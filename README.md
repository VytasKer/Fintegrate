# Fintegrate

Controlled learning environment for mastering software integration architecture.

## Project Purpose
Simulate a financial microservice ecosystem centered around customer management and message-driven communication. All modules are locally contained, with future expansion toward Azure integration and Power BI analytics.

## Architecture
Client (Postman) → Microservice (FastAPI) → Database (PostgreSQL) → Message Broker (RabbitMQ/Kafka) → API Gateway → Analytics (Airflow, Power BI) → Container Orchestration (Docker, Kubernetes)

## Setup Instructions
1. Install PostgreSQL and create database on port 5435
2. Configure `.env` file with database credentials
3. Install Python dependencies: `pip install -r requirements.txt`
4. Run database migrations from `/database/migrations/`
5. Start customer service: `cd services/customer_service && uvicorn main:app --reload`

## Documentation
- `project-context.txt` - Project overview and learning plan
- `database-context.txt` - Database schema and migration procedures
- `copilot-instructions.txt` - AI assistant operational guidelines
