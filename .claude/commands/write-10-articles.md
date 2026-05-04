# Write 10 Articles Command

Use this command to analyze Valencia Theater Seating's website, choose the right
number of SEO article topics, then generate Shopify-ready HTML articles with two
generated images per article.

## Usage
`/write-10-articles [company context or campaign brief]`

## What This Command Does
1. Acts as an SEO topic strategy agent for Valencia Theater Seating
2. Analyzes `https://valenciatheaterseating.com/` by default when no custom input is provided
3. Chooses between 5 and 20 article topics based on the website analysis, buyer intent, and ecommerce conversion potential
4. Uses `/shopify-with-images` for each selected topic
5. Generates two relevant images per article
6. Uploads each article HTML file and its two images to Google Cloud Storage
7. Returns the selected topic count, selected topics, and upload metadata in the API response

## Topic Selection Requirements

Topics should be relevant to:
- Valencia Theater Seating
- Premium home theater seating
- Theater recliners
- Theater sofas and sectionals
- Media room design
- Luxury entertainment rooms
- Home cinema planning
- Seating layouts, sizing, materials, features, and buyer comparisons

Prioritize topics that can drive ecommerce discovery and conversion, such as:
- Buying guides
- Comparison articles
- Room planning guides
- Material and feature explainers
- Layout and sizing guides
- Premium/luxury home theater design topics

Avoid unrelated automotive, generic furniture, generic SEO, or non-home-theater topics unless explicitly requested.

## Output

The API returns:
- The number of articles the AI agent chose to create
- The topics selected by the AI agent
- The primary keyword, angle, and reason for each topic
- The generated article upload metadata
- The two image upload URLs per article
- Any per-topic errors if a specific article fails

Each article is generated through `/shopify-with-images`, so it must preserve:

```html
<div class="article-in-this-article">
```

at the top of the Shopify HTML.
