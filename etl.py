import os
import sys
import time
import sqlite3
import requests
import pandas as pd

DB_NAME = "movies.db"
RATING_COLUMNS = ["userId", "movieId", "rating", "timestamp"]

def extract_and_transform():
    print("Reading CSV files...")
    try:
        movies_df = pd.read_csv("movies.csv")
        ratings_df = pd.read_csv("ratings.csv")
        links_df = pd.read_csv("links.csv", dtype={"imdbId": "string"})
    except FileNotFoundError as e:
        print(f"CRITICAL: Missing data file. Ensure movies.csv, ratings.csv, and links.csv are present.\nDetails: {e}")
        sys.exit(1)

    print("Transforming core data...")
    
    # Extract year and calculate decade as nullable integers
    year = movies_df["title"].str.extract(r"\((\d{4})\)\s*$")[0]
    movies_df["release_year"] = pd.to_numeric(year, errors="coerce").astype("Int64")
    movies_df["release_decade"] = (movies_df["release_year"] // 10 * 10).astype("Int64")
    
    # Merge IMDb IDs and enforce 1:1 validation on the movieId join key
    movies_df = movies_df.merge(
        links_df[["movieId", "imdbId"]],
        on="movieId",
        how="left",
        validate="one_to_one"
    )
    
    # Format IMDB ID to OMDb standard
    movies_df["imdb_id"] = movies_df["imdbId"].apply(
        lambda x: f"tt{x.zfill(7)}" if pd.notna(x) and str(x).isdigit() else None
    )
    
    # Initialize enrichment columns
    movies_df['director'] = None
    movies_df['plot'] = None
    movies_df['box_office_usd'] = None

    api_key = os.getenv("OMDB_API_KEY")
    if not api_key:
        print("CRITICAL: OMDB_API_KEY environment variable is missing. This pipeline requires the OMDb API to run.")
        sys.exit(1)
    else:
        print("Fetching OMDb details (will safely exit enrichment if daily limit is reached)...")
        failed_api_calls = 0
        
        for index, row in movies_df.iterrows():
            imdb_id = row['imdb_id']
            if pd.isna(imdb_id):
                continue
                
            url = f"https://www.omdbapi.com/?i={imdb_id}&apikey={api_key}"
            
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data.get("Response") == "True":
                    director = data.get('Director')
                    movies_df.at[index, 'director'] = None if director == "N/A" else director
                    
                    plot = data.get('Plot')
                    movies_df.at[index, 'plot'] = None if plot == "N/A" else plot
                    
                    bo_str = data.get('BoxOffice', 'N/A')
                    if bo_str not in ('N/A', None):
                        bo_clean = bo_str.replace('$', '').replace(',', '')
                        if bo_clean.isdigit():
                            movies_df.at[index, 'box_office_usd'] = int(bo_clean)
                            
                else:
                    error_msg = data.get("Error", "").lower()
                    if "invalid api key" in error_msg:
                        print("CRITICAL: Invalid OMDb API key provided. Authentication failed.")
                        sys.exit(1)
                    elif "limit" in error_msg:
                        print(f"\nAPI Limit reached at index {index}. Proceeding to load phase...")
                        break
                        
                    failed_api_calls += 1
                        
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (401, 403):
                    # Check if OMDb is returning a rate limit disguised as a 401
                    if "limit" in e.response.text.lower():
                        print(f"\nAPI Limit reached at index {index}. Proceeding to load phase...")
                        break
                    else:
                        print(f"CRITICAL: Invalid OMDb API key provided. Authentication failed (HTTP {e.response.status_code}).")
                        sys.exit(1)
                failed_api_calls += 1
                
            time.sleep(0.08)

            if index > 0 and index % 50 == 0:
                print(f"Processed {index} movies...")
            
        if failed_api_calls > 0:
            print(f"Note: {failed_api_calls} API enrichment requests failed or returned unsuccessful responses.")

    print("Cleaning downstream relational data...")
    for col in RATING_COLUMNS:
        ratings_df[col] = pd.to_numeric(ratings_df[col], errors="coerce")
    
    ratings_df = ratings_df.dropna(subset=RATING_COLUMNS)
    ratings_df = ratings_df[(ratings_df['rating'] >= 0.5) & (ratings_df['rating'] <= 5.0)]
    
    # Ensure IDs and timestamps are strictly integers before casting, preventing silent truncation
    for col in ["userId", "movieId", "timestamp"]:
        ratings_df = ratings_df[ratings_df[col] % 1 == 0]
        ratings_df[col] = ratings_df[col].astype(int)

    return movies_df, ratings_df

def to_db_records(df, columns):
    records = []
    for row in df[columns].itertuples(index=False):
        clean_row = tuple(
            None if pd.isna(x) else (x.item() if hasattr(x, "item") else x) 
            for x in row
        )
        records.append(clean_row)
    return records

def load_data(movies_df, ratings_df):
    print("Connecting to SQLite database...")
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    try:
        with open('schema.sql', 'r') as f:
            cursor.executescript(f.read())

        print("Loading Movies...")
        movies_records = to_db_records(
            movies_df, 
            ['movieId', 'imdb_id', 'title', 'release_year', 'release_decade', 'director', 'plot', 'box_office_usd']
        )
        
        cursor.executemany('''
            INSERT INTO movies (movie_id, imdb_id, title, release_year, release_decade, director, plot, box_office_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(movie_id) DO UPDATE SET
                imdb_id = COALESCE(excluded.imdb_id, movies.imdb_id),
                title = excluded.title,
                release_year = excluded.release_year,
                release_decade = excluded.release_decade,
                director = COALESCE(excluded.director, movies.director),
                plot = COALESCE(excluded.plot, movies.plot),
                box_office_usd = COALESCE(excluded.box_office_usd, movies.box_office_usd);
        ''', movies_records)

        print("Loading Genres...")
        genres_df = movies_df[['movieId', 'genres']].copy()
        genres_df['genre'] = genres_df['genres'].str.split('|')
        genres_df = genres_df.explode('genre')
        
        # Safely drop nulls, empty strings, and the placeholder
        genres_df = genres_df.dropna(subset=['genre'])
        genres_df['genre'] = genres_df['genre'].str.strip()
        genres_df = genres_df[(genres_df['genre'] != '') & (genres_df['genre'] != '(no genres listed)')]
        
        genres_records = to_db_records(genres_df, ['movieId', 'genre'])
        
        cursor.executemany('''
            INSERT OR IGNORE INTO movie_genres (movie_id, genre)
            VALUES (?, ?)
        ''', genres_records)

        print("Loading Ratings...")
        valid_movie_ids = movies_df['movieId'].unique()
        filtered_ratings = ratings_df[ratings_df['movieId'].isin(valid_movie_ids)]
        
        ratings_records = to_db_records(filtered_ratings, RATING_COLUMNS)
        
        cursor.executemany('''
            INSERT OR IGNORE INTO ratings (user_id, movie_id, rating, timestamp)
            VALUES (?, ?, ?, ?)
        ''', ratings_records)

        conn.commit()
        print("Data loading complete. Pipeline finished.")
        
    except Exception as e:
        conn.rollback()
        print(f"CRITICAL ERROR during database load: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    transformed_movies, raw_ratings = extract_and_transform()
    load_data(transformed_movies, raw_ratings)