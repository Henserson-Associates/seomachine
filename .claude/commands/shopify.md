# Shopify Command

Use this command to create a Shopify-ready article HTML fragment from a topic,
research brief, draft, or existing Markdown file.

## Usage
`/shopify [topic or article file]`

## What This Command Does
1. Creates or converts article content into Shopify-compatible HTML
2. Outputs a paste-ready HTML fragment, not a full HTML document
3. Preserves clear SEO article structure with H1/H2/H3 hierarchy
4. Includes a required "In this article" navigation block at the very top
5. Uses Shopify-safe tags and classes that match the provided sample format

## Critical Output Requirement

The first element in the output must be:

```html
<div class="article-in-this-article">
```

Do not forget this block. It must appear before the `<h1>`.

The block should follow this structure:

```html
<div class="article-in-this-article">
<p><strong>In this article: [short preview of the article]...</strong></p>
<ol>
<li>[Main section 1]</li>
<li>[Main section 2]</li>
<li>[Main section 3]</li>
<li>[Main section 4]</li>
<li>Frequently Asked Questions<br></li>
</ol>
</div>
```

## HTML Format Rules

Output only the Shopify article HTML fragment:
- Do not include `<!doctype html>`, `<html>`, `<head>`, or `<body>`
- Do not wrap the answer in Markdown code fences
- Do not include explanatory text before or after the HTML
- Use plain Shopify-safe HTML tags: `<h1>`, `<h2>`, `<h3>`, `<p>`, `<strong>`, `<em>`, `<ul>`, `<ol>`, `<li>`, `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`, `<a>`, `<img>`, `<hr>`
- Use `<table class="e-rte-table">` for tables
- Use `<hr>` between major sections where helpful
- Use `<p><img src="..." alt=""></p>` for images if image URLs are available
- Use `rel="noopener noreferrer"` and `target="_blank"` for external links
- Keep internal Shopify links as relative paths when appropriate, such as `/collections/...` or `/pages/...`
- Use HTML entities where needed, such as `&amp;`

## Content Structure

### 1. Required Top Navigation Block
Create the required `<div class="article-in-this-article">` block with:
- A bold one-sentence preview
- An ordered list of the main article sections
- 5-9 list items, depending on article length
- A FAQ item if the article includes FAQs

### 2. H1
Use one `<h1>` only.

### 3. Direct Answer Introduction
Open with a direct answer in the first paragraph. Use `<strong>` for the main
answer sentence when natural.

### 4. Quick Takeaways
Include:

```html
<h2>Quick Takeaways</h2>
<ul>
...
</ul>
```

### 5. Main Body
Use well-structured `<h2>` and `<h3>` sections. Include:
- Practical buying or decision guidance
- Clear comparisons where useful
- Tables for structured information
- Internal links and contextual CTAs when available
- Evidence and references for factual claims

### 6. FAQ
Include a FAQ section when the topic is search-driven or buyer-focused:

```html
<h2>Frequently Asked Questions</h2>
<h3>[Question]</h3>
<p>[Answer]</p>
```

### 7. References
If the content cites external sources, include a references section:

```html
<h2>References</h2>
<ol>
<li><a rel="noopener noreferrer" href="..." target="_blank">Source name</a></li>
</ol>
```

## Conversion Rules

If the input is an existing Markdown article:
- Convert Markdown headings to HTML headings
- Convert Markdown lists to `<ul>` or `<ol>`
- Convert Markdown links to `<a>` tags
- Convert Markdown tables to `<table class="e-rte-table">`
- Convert bold/italic Markdown to `<strong>` and `<em>`
- Remove Markdown frontmatter and metadata blocks unless they belong in the article
- Preserve the article's meaning, section order, and SEO intent
- Add the required `<div class="article-in-this-article">` block if missing

If the input is a topic:
- Write the full article directly in Shopify HTML
- Follow the research, writing, brand voice, and SEO context files
- Make the article publish-ready

## Output

Return only the final Shopify HTML fragment. The API will save it as:

`output/shopify-[topic-or-file-slug]-[YYYY-MM-DD].html`
