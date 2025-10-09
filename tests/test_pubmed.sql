'''
Queries checking pubmed data ingestion
sqlite3 tracker.db <query>
'''

-- People
SELECT id, first_name, last_name 
FROM people 
LIMIT 5;

-- Projects
SELECT *
FROM projects 
WHERE source='pubmed' 
LIMIT 5;

-- Publications
SELECT pmid, title 
FROM pubs 
ORDER BY id DESC 
LIMIT 5;

-- Publication by PI
SELECT pe.first_name||' '||pe.last_name AS person,
                  COUNT(pb.id) AS n_pubs
FROM people pe
LEFT JOIN people_project_relation x ON x.person_id = pe.id
LEFT JOIN project_pub_relation y ON y.project_id = x.project_id
LEFT JOIN pubs pb ON pb.id = y.pub_id
GROUP BY pe.id
ORDER BY n_pubs DESC;