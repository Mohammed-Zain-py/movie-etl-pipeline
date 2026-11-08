# Movie Data ETL Pipeline

## 1. Project Overview

This project is an Extract, Transform, and Load (ETL) pipeline that processes the MovieLens small dataset, enriches it with external movie details from the OMDb API, and loads the processed data into a relational SQLite database.

The pipeline is built using Python (`pandas` for data transformation and `requests` for API calls) and is designed to handle missing data and safe reruns.

## 2. Repository Structure

As requested, the repository follows this structure:

```text
your-repo-name/
├── etl.py
├── schema.sql
├── queries.sql
└── README.md
```

*(Note: To run the project, `movies.csv`, `ratings.csv`, and `links.csv` must also be present in this folder).*

## 3. Setup and How to Run

### Prerequisites

* Python 3.x
* Required libraries: `pip install pandas requests`
* The MovieLens small dataset downloaded and placed in the project folder.
* SQLite command-line tool (for running the SQL queries from the terminal).

### Step 1: Configure the API Key

Get a free API key from OMDb. Set it as an environment variable in your terminal before running the script so it isn't hardcoded into the Python file.

**Windows PowerShell:**
```powershell
$env:OMDB_API_KEY="your_api_key_here"
```

**macOS / Linux:**
```bash
export OMDB_API_KEY="your_api_key_here"
```

### Step 2: Run the Pipeline

Execute the Python script. The script will print periodic progress messages and generate a `movies.db` SQLite database file.

```bash
python etl.py
```

### Step 3: Run the Analytics

Once the pipeline finishes and the database is created, you can run the SQL queries to answer the analytical questions:

```bash
./sqlite3 movies.db ".mode box" ".read queries.sql"
```

## 4. Design Choices and Assumptions

### Database Tables

I divided the data into three tables based on how the information is related:

* **`movies`**: Stores the core MovieLens data alongside the OMDb enrichment data (director, plot, box office). Feature Engineering (Bonus): I also extracted the release year from movie titles and calculated a release decade for each movie.
* **`movie_genres`**: Because a single movie can have multiple genres, this table stores one row per movie-genre combination to make querying by genre easier.
* **`ratings`**: Stores individual user ratings linked to the `movies` table via `movie_id`.

### Primary Keys and `links.csv`

Even though the assignment primarily mentions `movies.csv` and `ratings.csv`, `links.csv` is required to accurately match MovieLens records to OMDb records via the `imdb_id`. 
However, multiple MovieLens `movie_id`s can sometimes map to the same `imdb_id`. To prevent conflicts, I used the MovieLens `movie_id` as the Primary Key in the database to preserve the original source data structure.

### Missing Data Handling

If a release year cannot be parsed from the title, or if OMDb does not return a value for director, plot, or box office, the script leaves these fields empty (`NULL` in the database). Movies that are not found in OMDb, or do not have an available IMDb ID, are still retained using their available MovieLens information, with unavailable enrichment fields stored as `NULL`.

### Idempotency (Safe Reruns)

The pipeline is designed to be rerun safely. Rerunning with the same source data avoids duplicate records. It uses SQLite's `INSERT ... ON CONFLICT DO UPDATE` for movies, and `INSERT OR IGNORE` for genres and ratings. I also used the SQL `COALESCE` function to ensure that if a rerun fails to fetch OMDb data, it doesn't overwrite existing database records with `NULL`s.

## 5. Challenges and How They Were Handled

**Challenge: Matching MovieLens Titles with OMDb**
**Solution:** My initial approach was to clean the movie titles using regular expressions and use the cleaned titles along with release years to query the OMDb API. However, this approach involved several title-cleaning rules for alternate titles, trailing articles, and other variations, and still couldn't reliably avoid mismatches. While exploring the dataset further, I discovered that `links.csv` contained an `imdb_id` mapping for each MovieLens `movie_id`. I changed the approach to use these IMDb IDs directly for OMDb lookups instead of relying on title matching. This made the enrichment process more reliable and eliminated the need for the additional title-cleaning logic.

**Challenge: API Request Pacing and Rate Limits**
**Solution:** I added a small delay (`time.sleep(0.08)`) between API requests to introduce a short pause between consecutive calls. If the API returns a rate-limit error, the script stops further API calls and proceeds with loading the MovieLens data and any OMDb information successfully retrieved up to that point.

**Challenge: Missing or Invalid API Keys**
**Solution:** If the environment variable is missing, the script exits immediately. If OMDb reports an invalid API key, either through its API response or an HTTP 401/403 response, the script exits with a critical error. If the response indicates an API limit instead, the script stops further API requests and proceeds to the database loading phase.

**Challenge: Data Types for SQL**
**Solution:** pandas often converts missing integer data to floats (`NaN`). I added cleaning steps to handle missing and invalid values before loading the data. Rating values are checked against the valid range, and user IDs, movie IDs, and timestamps are checked to ensure they contain whole numbers. Missing release years are retained as `NULL` rather than using placeholder values.

## 6. Analytical Queries

The `queries.sql` file contains four queries. For the top-rated movie and top-rated genres queries, I added a `HAVING review_count >= X` threshold (5 for movies, 10 for genres). This is an analytical choice made to ensure that movies or genres with only one or two 5.0-star reviews do not unfairly dominate the results.