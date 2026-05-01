# Shopify With Images Command

Use this command to create a Shopify-ready HTML article, generate two relevant
images, insert them into the article, and upload the HTML and image assets to
Google Cloud Storage.

## Usage
`/shopify-with-images [topic or article file]`

## What This Command Does
1. Generates Shopify article HTML using the `/shopify` format rules
2. Creates two article-relevant images with OpenAI image generation
3. Uploads both images to Google Cloud Storage
4. Inserts the uploaded image URLs into the Shopify HTML
5. Uploads the final HTML file to Google Cloud Storage

## HTML Requirements

The final HTML must be a Shopify article body fragment, not a full HTML page.

The first element must be:

```html
<div class="article-in-this-article">
```

Do not forget this block. It must appear before the `<h1>`.

## Image Requirements

Generate exactly two images:
- One hero-style editorial image near the introduction
- One supporting in-article image near a later section

Images should be:
- Directly related to the article content
- Editorial and premium, suitable for a Shopify blog
- Free of visible text, watermarks, logos, and UI screenshots unless explicitly requested
- Inserted with Shopify-safe HTML:

```html
<p><img src="[uploaded-image-url]" alt=""></p>
```

## Output

The API returns the final HTML and upload metadata. The backend saves:

- `output/shopify-with-images-[slug]-[YYYY-MM-DD].html`
- `output/shopify-[slug]-[YYYY-MM-DD]-image-1.png`
- `output/shopify-[slug]-[YYYY-MM-DD]-image-2.png`

The backend also uploads those assets to the configured Google Cloud Storage
bucket.
