# DevOps Portal

A modern React + Vite based DevOps Portal for internal engineering teams.

## Features

- Role-based access (Developer / DevOps Admin)
- Home dashboard with welcome panel
- Global search
- Dashboard
- File Placement
- Monitoring
- Microservice (MS) Portal
- Admin approval screen
- Responsive UI

## Tech Stack

- React
- TypeScript
- Vite
- NGINX
- Docker

## Run Locally

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Docker

```bash
docker build -t devops-portal:v1 .
docker run -p 8080:8080 devops-portal:v1
```

## Project Structure

```
src/
 ├── components/
 ├── pages/
 ├── layouts/
 ├── hooks/
 ├── styles/
 └── utils/
```

## Future Enhancements

- Azure AD Authentication
- Azure DevOps Integration
- Kubernetes Monitoring
- Approval Workflows
- File Placement Automation
- RabbitMQ & Cluster Health Monitoring

## GTB Operations Agent

The DevOps-only **GTB Operations Agent** adds reference-aligned GTB/Collections
delivery plans and scoped, read-only Kubernetes investigations with persistent
history. Existing pipeline and release execution paths are preserved.

See [the repository analysis, configuration and agentic solution](docs/gtb-agentic-solution.md)
for the implemented scope, Collections-Dashboard reference contracts, rollout
requirements, tests and the path to model-driven delivery automation.
