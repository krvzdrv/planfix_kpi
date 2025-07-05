-- Запрос для получения структуры таблицы kpi_metrics
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'kpi_metrics' 
ORDER BY ordinal_position;

-- Запрос для получения примера данных из таблицы kpi_metrics
SELECT * FROM kpi_metrics LIMIT 5; 