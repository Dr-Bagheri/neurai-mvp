-- D4 data lifecycle: per-meeting sensitivity. A meeting marked «محرمانه»
-- (confidential) is local-only forever: excluded from cross-meeting indexing
-- and from backups, and its allow_cloud flag is forced off in the API.
ALTER TABLE meetings ADD COLUMN sensitivity TEXT NOT NULL DEFAULT 'normal';
