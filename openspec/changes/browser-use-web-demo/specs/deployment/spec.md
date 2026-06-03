## ADDED Requirements

### Requirement: Local development run
The system SHALL support running the application locally with a single command (`python main.py`), which starts the FastAPI server serving both the API and the built frontend static files.

#### Scenario: Start application locally
- **WHEN** user runs `python main.py`
- **THEN** the FastAPI server starts on port 8000, serving the Vue frontend at `/` and API endpoints at `/api/`

### Requirement: Docker deployment
The system SHALL provide a Dockerfile and docker-compose.yml for containerized deployment. The Docker image SHALL include Chromium for local browser mode.

#### Scenario: Deploy with Docker Compose
- **WHEN** user runs `docker-compose up`
- **THEN** the application starts in a container with Chromium available, accessible on the configured port

#### Scenario: Docker image includes Chromium
- **WHEN** the Docker container starts in local browser mode
- **THEN** Chromium is available for browser-use to launch without additional setup

### Requirement: Frontend build integration
The system SHALL include the Vue frontend build as part of the deployment process. The built static files SHALL be served by FastAPI.

#### Scenario: Frontend is served by FastAPI
- **WHEN** a request is made to the root URL
- **THEN** FastAPI serves the Vue frontend's index.html and static assets

#### Scenario: Frontend build step in Docker
- **WHEN** the Docker image is built
- **THEN** the Vue frontend is built using Node.js and the output is copied into the FastAPI static directory
