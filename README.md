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


## Datasource management

The Datasources page supports an admin-managed application/environment catalog and WebLogic datasource execution through Azure DevOps + WLST.

For TXCSIT, admins can use **Load TXCSIT Defaults** while adding an application environment. The portal fills the supplied application host mapping, `/azure_artifact` paths, default database host `gtbtxcoreobpmdbsit.uat.mashreqdev.com:1531`, and ONS nodes. BASE, domain, WebLogic/SSH users, passwords, and any application-specific values still require admin verification before saving.

Stored WebLogic and SSH passwords are never returned to the browser. The datasource workspace shows only masked credential state, while displaying the selected application's runtime configuration, database defaults, and pipeline result overview (created datasource count and names).
