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
