# AWS resources (Member 3)

| Resource   | Purpose                                                     | Name (fill in)        |
|------------|-------------------------------------------------------------|-----------------------|
| (S3)       | not needed: data, DVC and MLflow live on DagsHub            | —                     |
| ECR        | API / dashboard / pipeline images                           | `solarcast-api`       |
| EC2        | runs API (+ dashboard) containers                           |                       |
| CloudWatch | app logs, request errors, inference latency                 | `/solarcast/api`      |
| IAM        | EC2 instance role, GitHub OIDC role, per-member users       |                       |

Put IAM policy JSONs and EC2 user-data scripts in this folder. Never commit access keys.
