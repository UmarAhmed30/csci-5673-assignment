USE product_db;
ALTER TABLE cart ADD COLUMN saved BOOLEAN DEFAULT FALSE;
UPDATE cart SET saved = TRUE;
SELECT 'Migration completed successfully!' AS status;
