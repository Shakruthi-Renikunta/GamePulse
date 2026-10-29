# AWS deployment design — not deployed

Target architecture: HTTPS load balancer → ECS Fargate API tasks → private RDS PostgreSQL and ElastiCache Redis. Store secrets in Secrets Manager. Export logs to CloudWatch and scrape per-task Prometheus metrics through an appropriate monitoring setup. Game servers invoke the results API with service credentials.

The current Compose setup is a local development environment. No AWS account access, resources, Terraform, automated deployment workflow, or production performance results are included.

Before implementing deployment:

1. Add Alembic migrations and run a one-off migration task before rolling out API tasks.
2. Build and push the tested image to ECR, using an immutable commit SHA tag.
3. Configure private networking and security groups so only API tasks access the database/cache. Restrict the result endpoint to trusted game-server access.
4. Use HTTPS, database/cache TLS settings, secret injection, login throttling, backup/restore procedures, and a production readiness policy.
5. Configure ECS health checks, load balancer targets, resource limits, timeouts, rollback, and explicit per-replica metric scraping.
6. Use GitHub OIDC with narrowly scoped AWS IAM roles for deployment; do not put long-lived AWS credentials in the repository.
7. Deploy to staging, run authenticated integration/load tests, record results, and validate rollback before production.

AWS services incur charges. Select region, budget, and networking requirements before provisioning anything. No cloud spending is required for the local interview demo.
