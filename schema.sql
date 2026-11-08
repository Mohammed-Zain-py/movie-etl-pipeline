-- Movie details and API enrichment
CREATE TABLE IF NOT EXISTS movies (
    movie_id INTEGER PRIMARY KEY,
    imdb_id TEXT,             -- No UNIQUE constraint to preserve source movieId integrity
    title TEXT NOT NULL,
    release_year INTEGER,
    release_decade INTEGER,
    director TEXT,
    plot TEXT,
    box_office_usd INTEGER
);

-- One row per movie-genre relationship
CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id INTEGER NOT NULL,
    genre TEXT NOT NULL,
    PRIMARY KEY (movie_id, genre),
    FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
);

-- User ratings for movies
CREATE TABLE IF NOT EXISTS ratings (
    user_id INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    rating REAL NOT NULL CHECK (rating BETWEEN 0.5 AND 5.0),
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (user_id, movie_id),
    FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE
);

-- Index to optimize analytical queries filtering by movie
CREATE INDEX IF NOT EXISTS idx_ratings_movie_id
ON ratings(movie_id);