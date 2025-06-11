-- Создание таблицы для хранения плановых показателей выручки
CREATE TABLE IF NOT EXISTS revenue_plans (
    id SERIAL PRIMARY KEY,
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    revenue_plan DECIMAL(15,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(month, year)
);

-- Создание индекса для быстрого поиска по месяцу и году
CREATE INDEX IF NOT EXISTS idx_revenue_plans_month_year ON revenue_plans(month, year);

-- Добавление комментариев к таблице и колонкам
COMMENT ON TABLE revenue_plans IS 'Таблица для хранения плановых показателей выручки по месяцам';
COMMENT ON COLUMN revenue_plans.month IS 'Месяц (1-12)';
COMMENT ON COLUMN revenue_plans.year IS 'Год';
COMMENT ON COLUMN revenue_plans.revenue_plan IS 'Плановое значение выручки в PLN'; 