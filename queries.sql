-- queries.sql

-- 1. Which movie has the highest average rating?
-- (Filtering for movies with at least 5 reviews so a movie with a single 5-star review doesn't win)
SELECT m.title, AVG(r.rating) as avg_rating, COUNT(r.rating) as review_count
FROM movies m
JOIN ratings r ON m.movie_id = r.movie_id
GROUP BY m.movie_id, m.title
HAVING review_count >= 5
ORDER BY avg_rating DESC
LIMIT 1;

-- 2. What are the top 5 movie genres that have the highest average rating?
SELECT mg.genre, AVG(r.rating) as avg_rating, COUNT(r.rating) as review_count
FROM movie_genres mg
JOIN ratings r ON mg.movie_id = r.movie_id
GROUP BY mg.genre
HAVING review_count >= 10
ORDER BY avg_rating DESC
LIMIT 5;

-- 3. Who is the director with the most movies in this dataset?
SELECT director, COUNT(movie_id) as total_movies
FROM movies
WHERE director IS NOT NULL
GROUP BY director
ORDER BY total_movies DESC
LIMIT 1;

-- 4. What is the average rating of movies released each year?
SELECT m.release_year, AVG(r.rating) as avg_rating
FROM movies m
JOIN ratings r ON m.movie_id = r.movie_id
WHERE m.release_year IS NOT NULL
GROUP BY m.release_year
ORDER BY m.release_year;