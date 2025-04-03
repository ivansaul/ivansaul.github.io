import asyncio
from datetime import date
from pathlib import Path

import aiohttp
import frontmatter  # type: ignore
import yaml  # type: ignore
from pydantic import BaseModel, Field
from rich import print

BLOG_URL = "https://ivansaul.github.io/blog"
RAW_BASE_URL = "https://raw.githubusercontent.com/ivansaul/blog/master"
MKDOCS_URL = RAW_BASE_URL + "/mkdocs.yaml"


class PostFrontMatter(BaseModel):
    title: str
    description: str
    published: date = Field(alias="date")
    image: str


class BlogPostFrontMatter(PostFrontMatter):
    category: str
    url: str
    published: date = Field(alias="date")


async def fetch(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()


def flatten_dict(data: list) -> dict:
    result = {}

    def extract_urls(key, value):
        if key not in result:
            result[key] = []

        for item in value:
            if isinstance(item, str):
                if not item.endswith("index.md"):
                    result[key].append(item)
            elif isinstance(item, dict):
                for subkey, subvalue in item.items():
                    extract_urls(key, subvalue)

    for entry in data:
        for main_key, values in entry.items():
            extract_urls(main_key, values)

    return result


async def fetch_toc() -> dict[str, list[str]]:
    """
    Fetch the table of contents from the mkdocs.yaml file.

    Returns:
        dict[str, list[str]]: A dictionary containing the table of contents.

    Example:
        >>> toc = await fetch_toc()
        >>> print(toc)
        {
            'swift': [
                'swift/continued-learning/how-to-sort-arrays-in-swift.md',
                'swift/continued-learning/extensions-in-swift.md',
                ...
            ],
            'swiftui': [
                'swiftui/swiftui-text.md',
                'swiftui/how-to-add-custom-fonts-in-swiftui.md',
                ...
            ],
            ...
        }
    """
    resp = await fetch(MKDOCS_URL)
    content = yaml.safe_load(resp.replace("!", ""))
    nav = content["nav"]
    return flatten_dict(nav)


async def fetch_frontmatter(url: str) -> PostFrontMatter:
    resp = await fetch(url)
    post = frontmatter.loads(resp)
    return PostFrontMatter.model_validate(post.metadata)


async def fetch_and_process_metadata(category: str, src: str) -> BlogPostFrontMatter:
    md_url = f"{RAW_BASE_URL}/docs/{src}"
    md_path = Path(src).with_suffix("").as_posix()
    post_url = f"{BLOG_URL}/{md_path}"

    frontmatter = await fetch_frontmatter(md_url)
    frontmatter.image = f"{RAW_BASE_URL}/docs/{frontmatter.image}"

    return BlogPostFrontMatter(
        title=frontmatter.title,
        description=frontmatter.description,
        date=frontmatter.published,
        image=frontmatter.image,
        category=category,
        url=post_url,
    )


async def main():
    toc = await fetch_toc()
    tasks = []

    for key, value in toc.items():
        for item in value:
            tasks.append(fetch_and_process_metadata(key, item))

    results: list[BlogPostFrontMatter] = []
    errors: list[str] = []

    for future in asyncio.as_completed(tasks):
        try:
            result: BlogPostFrontMatter = await future
            results.append(result)
            print(f"[green][{len(results)} / {len(tasks)}] {result.title}[/green]")
        except Exception as e:
            errors.append(str(e))

    if errors:
        for error in errors:
            print(f"[red]Error: {error}[/red]")
        return

    results.sort(key=lambda x: x.published, reverse=True)

    with open("config/blog.yml", "w") as f:
        f.write("HEADER:\n")
        f.write('  label: "Blog"\n')
        f.write("\n")
        f.write("POSTS:\n")
        for result in results:
            f.write(f'  - title: "{result.title}"\n')
            f.write(f'    category: "{result.category}"\n')
            f.write(f'    subtitle: "{result.description}"\n')
            f.write(f'    published: "{result.published}"\n')
            f.write(f'    image: "{result.image}"\n')
            f.write(f'    url: "{result.url}"\n')
            f.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
