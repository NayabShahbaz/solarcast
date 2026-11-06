# Switching storage from DagsHub to AWS S3

**Owner:** Member 1 (data), with Member 3 (AWS account, IAM, EC2)
**Takes:** about 30–60 minutes, plus a day of running both side by side
**Why:** the proposal commits to AWS S3. DagsHub is a temporary stand-in so data work isn't
blocked waiting for AWS access.

Nothing in `src/` changes. The switch only touches `.env`, `.dvc/config` and AWS resources,
because both DVC and `solarcast.data.storage` already use the S3 API.

---

## 0. Before you start

- [ ] Member 3 has an AWS account, with an **AWS Budget alert** set (e.g. $5/month).
- [ ] AWS CLI v2 is installed: `aws --version`.
- [ ] Your DagsHub token still works: `dvc pull` succeeds.
- [ ] All local data is pushed: `dvc status -c` shows nothing to push.
- [ ] Teammates know not to `dvc push` during the switch.

## 1. Create the bucket (Member 3)

Use **ap-south-1 (Mumbai)**, the closest region to Lahore.

```bash
aws s3api create-bucket --bucket solarcast-data --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1
aws s3api put-public-access-block --bucket solarcast-data \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Bucket names are global. If `solarcast-data` is taken, use something like
`solarcast-data-bcs7a` and use that name everywhere below.

Layout inside the bucket:

```
s3://solarcast-data/
├── dvc/          DVC remote (content-addressed, don't touch by hand)
├── raw/          daily ingestion output
├── processed/    processed hourly dataset
└── monitoring/   Evidently reports + forecast-error JSON for the dashboard
```

## 2. Give each member access (Member 3)

Create an IAM policy `solarcast-data-rw`, save it as `infra/aws/iam_s3_policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::solarcast-data"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::solarcast-data/*"
    }
  ]
}
```

Attach it to:
- one IAM user per member (for laptops, via access keys),
- the **EC2 instance role** (no keys on the server),
- the **GitHub Actions OIDC role** (no keys in GitHub secrets).

## 3. Set up an AWS profile on your machine (each member)

```bash
aws configure --profile solarcast      # access key, secret, region ap-south-1, json
aws s3 ls s3://solarcast-data --profile solarcast    # must not error
```

## 4. Pull every dataset version from DagsHub (Member 1)

`--all-commits` gets the data for every commit, not just the current one, so old experiments
stay reproducible.

```bash
git checkout main && git pull
git fetch --all --tags
dvc pull -r origin --all-commits --all-tags
```

## 5. Add AWS as a second DVC remote and push everything (Member 1)

```bash
dvc remote add aws s3://solarcast-data/dvc
dvc remote modify --local aws profile solarcast
dvc push -r aws --all-commits --all-tags
```

The profile goes in `.dvc/config.local` (git-ignored), so each member can use their own.

## 6. Verify the AWS copy is complete

```bash
dvc status -c -r aws --all-commits     # expect: "Cache and remote 'aws' are in sync."
```

Then a fresh-clone test in a temporary folder:

```bash
git clone <github-url> solarcast-check && cd solarcast-check
dvc remote modify --local aws profile solarcast
dvc pull -r aws
```

Open the processed parquet and check the row count matches.

## 7. Copy the non-DVC objects (raw / processed / monitoring)

The DagsHub bucket is S3-compatible, so the AWS CLI can read it with a second profile.

```bash
aws configure --profile dagshub        # key AND secret = DagsHub token, region us-east-1
aws s3 sync s3://solarcast ./_migrate --profile dagshub \
  --endpoint-url https://dagshub.com/api/v1/repo-buckets/s3/<dagshub-user>
aws s3 sync ./_migrate s3://solarcast-data --profile solarcast --exclude "dvc/*"
```

Delete `./_migrate` once the counts match:
`aws s3 ls s3://solarcast-data --recursive --summarize --profile solarcast`.

## 8. Make AWS the default and commit

```bash
dvc remote default aws
git add .dvc/config
git commit -m "Switch DVC default remote to AWS S3"
git push
```

Keep `origin` (DagsHub) as a backup remote for now. See step 11.

## 9. Point the code at AWS

Update `.env` on every machine (see Option B in `.env.example`):

```ini
S3_ENDPOINT_URL=
S3_BUCKET=solarcast-data
AWS_PROFILE=solarcast
AWS_REGION=ap-south-1
# delete AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (those were the DagsHub token)
```

Quick check:

```bash
python -c "from solarcast.data import storage; print(storage.list_keys('processed/')[:5])"
```

Elsewhere:
- **EC2:** no `AWS_PROFILE` and no keys; the instance role provides credentials.
- **GitHub Actions:** set `AWS_REGION` and the role ARN as repo secrets. Remove any DagsHub token secrets.
- **Prefect:** if credentials are stored in a Prefect block, update it.
- **Then update `.env.example`:** make Option B the active block.

## 10. Tell the team (each member)

```bash
git pull
dvc remote modify --local aws profile solarcast
# update .env as in step 9
dvc pull
```

## 11. Remove DagsHub (about a week later, once nothing has broken)

```bash
dvc remote remove origin
git add .dvc/config && git commit -m "Remove DagsHub DVC remote" && git push
```

MLflow is a separate decision. See Part B below.

---

# Part B — MLflow: DagsHub → self-hosted on AWS (optional)

**Owner:** Member 2 (experiments, registry), with Member 3 (EC2, API)

The team uses DagsHub's hosted MLflow (`https://dagshub.com/<dagshub-user>/solarcast.mlflow`).
That still counts as "MLflow" from the proposal, so **moving it is optional**. Decide on one:

| Option | When to choose it | Work |
|--------|-------------------|------|
| **B1. Keep MLflow on DagsHub** (recommended) | Free tier is enough, no auth server to run | Only give EC2 the credentials (B1 below) |
| **B2. Self-host MLflow on EC2, artifacts in S3** | Instructor wants everything on AWS, or DagsHub limits are hit | Steps B2.1–B2.6 |

## B1. Keep DagsHub MLflow, use it from AWS

1. Store the DagsHub token in **AWS SSM Parameter Store** (SecureString), not in the Docker image:
   ```bash
   aws ssm put-parameter --name /solarcast/mlflow_password --type SecureString \
     --value <dagshub-token> --profile solarcast
   ```
2. Give the EC2 instance role `ssm:GetParameter` on `/solarcast/*`.
3. At container start, set `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME` and
   `MLFLOW_TRACKING_PASSWORD` (read from SSM) as environment variables.
4. In GitHub Actions (evaluation gate), add the same three values as repo secrets.

That's all. Skip B2.

## B2. Self-host MLflow on AWS

### B2.1 Run the MLflow server on EC2 (Member 3)

On the API instance, or a separate `t3.micro`:

```bash
pip install "mlflow>=2.9,<4" boto3
mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri sqlite:////opt/mlflow/mlflow.db \
  --artifacts-destination s3://solarcast-data/mlflow \
  --serve-artifacts
```

- Run it as a `systemd` service so it restarts with the instance.
- Add `s3:GetObject/PutObject/ListBucket` on `solarcast-data/mlflow/*` to the instance role.
  The bucket policy in step 2 already covers it.
- **MLflow has no login by default.** Open port 5000 only to the team's IPs in the security
  group, or reach it through an SSH tunnel: `ssh -L 5000:localhost:5000 ec2-user@<ec2-host>`.

### B2.2 Decide what history to move (Member 2)

Pick one:

- **(a) Minimal, recommended:** move only the registered model versions you need (current
  `production` plus the previous one, for rollback). Leave the full experiment history on DagsHub
  as a read-only record, and link it in the final report.
- **(b) Full copy:** move every experiment and run with the
  [`mlflow-export-import`](https://github.com/mlflow/mlflow-export-import) tool. Check its README
  for current command names before running.

### B2.3 Move the runs and models

For (b), export from DagsHub, then import into the new server:

```bash
pip install mlflow-export-import

# export from DagsHub
set MLFLOW_TRACKING_URI=https://dagshub.com/<dagshub-user>/solarcast.mlflow
set MLFLOW_TRACKING_USERNAME=<dagshub-user>
set MLFLOW_TRACKING_PASSWORD=<dagshub-token>
export-experiment --experiment solarcast --output-dir ./mlflow_export/exp
export-model --model solarcast-tft --output-dir ./mlflow_export/model

# import into AWS (clear the username/password vars first)
set MLFLOW_TRACKING_URI=http://<ec2-host>:5000
import-experiment --experiment-name solarcast --input-dir ./mlflow_export/exp
import-model --model solarcast-tft --experiment-name solarcast --input-dir ./mlflow_export/model
```

(Windows `set` shown; on macOS/Linux use `export`.)

For (a), it's simpler to rerun training against the new server: the dataset versions are in
DVC, so runs are reproducible.

```bash
set MLFLOW_TRACKING_URI=http://<ec2-host>:5000
dvc pull
python -m solarcast.flows.training_flow
```

Do this for the commits/tags of the current production model and the previous one.

### B2.4 Restore the aliases (Member 2)

Aliases don't always survive a move. Set them again in the new registry:

```python
from mlflow import MlflowClient
c = MlflowClient()
c.set_registered_model_alias("solarcast-tft", "production", "<new-version>")
c.set_registered_model_alias("solarcast-tft", "previous", "<older-version>")   # for rollback
```

### B2.5 Point everyone at the new server

- `.env` on every machine: `MLFLOW_TRACKING_URI=http://<ec2-host>:5000`, and delete
  `MLFLOW_TRACKING_USERNAME` / `MLFLOW_TRACKING_PASSWORD`.
- GitHub Actions secrets: same change.
- API container on EC2: `MLFLOW_TRACKING_URI=http://localhost:5000`, or the private IP if
  MLflow runs on a separate instance.
- `.env.example`: update the default block.

### B2.6 Verify

- [ ] `mlflow.search_registered_models()` lists `solarcast-tft` with `production` and `previous`
- [ ] API `/model-info` returns the expected version after a restart
- [ ] A new training run logs and its artifacts appear under `s3://solarcast-data/mlflow/`
- [ ] Rollback (`scripts/rollback.sh`) loads the `previous` model successfully
- [ ] Old DagsHub experiments are still readable (keep the token until the report is submitted)

---

## Rollback (if AWS breaks during the switch)

```bash
dvc remote default origin
git add .dvc/config && git commit -m "Revert DVC default to DagsHub" && git push
```

Then restore the Option A block in `.env`. Nothing was deleted from DagsHub, so this is safe
until step 11.

## Final checklist

- [ ] `dvc status -c -r aws --all-commits` is in sync
- [ ] Fresh clone + `dvc pull` works for every member
- [ ] `storage.list_keys()` returns objects from AWS
- [ ] Daily Prefect ingestion wrote to AWS at least once
- [ ] API on EC2 reads monitoring and forecast data with the instance role
- [ ] Dashboard shows the latest drift report
- [ ] DagsHub remote removed (after a week)
