# Deploy SEO Machine API to Google Cloud Run

This guide packages the FastAPI backend in Docker and deploys it to Cloud Run.
Cloud Run is a good fit because this project is an HTTP API that can run as a
stateless container.

## Important Storage Note

The API writes generated Markdown files to folders like `research/` and
`drafts/`. On Cloud Run, the container filesystem is temporary. Files written at
runtime can disappear when an instance restarts or scales down.

For production, treat the API response `content` as the durable result, or add
Google Cloud Storage persistence later. Local development still saves files to
your repo folders.

## Local Docker Test

Build the container:

```bash
docker build -t seo-machine-api .
```

Run it locally with your `.env` file:

```bash
docker run --rm -p 8080:8080 --env-file .env seo-machine-api
```

Open:

```text
http://127.0.0.1:8080/docs
```

Test a dry run:

```bash
curl -X POST http://127.0.0.1:8080/research \
  -H "Content-Type: application/json" \
  -d '{"input":"bmw dealerships toronto","dry_run":true,"save":false}'
```

## Google Cloud Prerequisites

Install and initialize the Google Cloud CLI:

```bash
gcloud init
```

Set your project and region:

```bash
export PROJECT_ID="your-google-cloud-project-id"
export REGION="us-central1"
export REPOSITORY="seo-machine"
export SERVICE="seo-machine-api"
export BUCKET="your-seo-machine-bucket"

gcloud config set project "$PROJECT_ID"
```

Enable required services:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com
```

Create an Artifact Registry Docker repository:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --description="SEO Machine API containers"
```

Create a Google Cloud Storage bucket for generated Shopify HTML and images:

```bash
gcloud storage buckets create "gs://$BUCKET" \
  --location="$REGION" \
  --uniform-bucket-level-access
```

If you want the returned `https://storage.googleapis.com/...` URLs to be public,
grant public read access:

```bash
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

If you keep the bucket private, use the returned `gs://...` URIs internally or
add signed URL support later.

Create a Secret Manager secret for your OpenAI key:

```bash
printf "%s" "$OPENAI_API_KEY" | gcloud secrets create openai-api-key \
  --data-file=-
```

If the secret already exists and you need to update it:

```bash
printf "%s" "$OPENAI_API_KEY" | gcloud secrets versions add openai-api-key \
  --data-file=-
```

Make sure the Cloud Run runtime service account can read the secret. This
example uses the default Compute Engine service account:

```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

If you deploy with a custom Cloud Run service account, grant
`roles/secretmanager.secretAccessor` to that service account instead.

Grant the Cloud Run runtime service account permission to upload objects:

```bash
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

## Deploy With Cloud Build

The included `cloudbuild.yaml` builds the Docker image, pushes it to Artifact
Registry, and deploys Cloud Run.

```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions _REGION="$REGION",_REPOSITORY="$REPOSITORY",_SERVICE="$SERVICE",_BUCKET="$BUCKET"
```

When the build finishes, get the service URL:

```bash
gcloud run services describe "$SERVICE" \
  --region "$REGION" \
  --format='value(status.url)'
```

Test the deployed service:

```bash
SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --region "$REGION" \
  --format='value(status.url)')"

curl "$SERVICE_URL/health"
```

If your service returns `"ANTHROPIC_API_KEY is required unless dry_run=true."`,
the deployed revision is missing `SEO_MACHINE_LLM_PROVIDER=openai` or is running
an older image. Set the Cloud Run environment variables and redeploy:

```bash
gcloud run services update "$SERVICE" \
  --region "$REGION" \
  --set-env-vars SEO_MACHINE_LLM_PROVIDER=openai,OPENAI_MODEL=gpt-5.2,SEO_MACHINE_MAX_TOKENS=12000,OPENAI_IMAGE_MODEL=gpt-image-1.5,OPENAI_IMAGE_SIZE=1536x1024,OPENAI_IMAGE_QUALITY=medium,OPENAI_IMAGE_EXTENSION=png,GOOGLE_CLOUD_STORAGE_BUCKET="$BUCKET" \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest
```

Run research:

```bash
curl -X POST "$SERVICE_URL/research" \
  -H "Content-Type: application/json" \
  -d '{"input":"bmw dealerships toronto","save":true}'
```

Generate Shopify HTML with two images and upload all assets:

```bash
curl -X POST "$SERVICE_URL/shopify-with-images" \
  -H "Content-Type: application/json" \
  -d '{"input":"bmw dealerships toronto","save":true}'
```

## Manual Build And Deploy

If you do not want to use `cloudbuild.yaml`, run these commands:

```bash
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/api:latest"

gcloud builds submit --tag "$IMAGE"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars SEO_MACHINE_LLM_PROVIDER=openai,OPENAI_MODEL=gpt-5.2,SEO_MACHINE_MAX_TOKENS=12000,OPENAI_IMAGE_MODEL=gpt-image-1.5,OPENAI_IMAGE_SIZE=1536x1024,OPENAI_IMAGE_QUALITY=medium,OPENAI_IMAGE_EXTENSION=png,GOOGLE_CLOUD_STORAGE_BUCKET="$BUCKET" \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest
```

## Security Notes

- Do not copy `.env` into Docker images. `.dockerignore` excludes it.
- Use Secret Manager for API keys.
- `--allow-unauthenticated` makes the API public. For private/internal use, remove
  that flag and configure Cloud Run IAM.
- The generated API docs are available at `/docs`; keep the service private if
  you do not want others discovering or using your generation endpoints.

## Official References

- Cloud Run container deployment: https://docs.cloud.google.com/run/docs/deploying
- `gcloud run deploy`: https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy
- Cloud Build to Cloud Run: https://docs.cloud.google.com/build/docs/deploying-builds/deploy-cloud-run
- Artifact Registry with Cloud Build: https://docs.cloud.google.com/build/docs/building/store-artifacts-in-artifact-registry
