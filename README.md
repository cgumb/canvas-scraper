# Canvas Module Scraper

This tool scrapes module content from Canvas courses, saving textual information as Markdown files and downloading associated files.

## Features

- Fetches content from specified Canvas courses or all accessible courses.
- Organizes content by Course > Module.
- Saves module text (from Pages, Assignments, etc.) into a `README.md` file within each module's folder.
- Converts HTML content to Markdown.
- Downloads files linked in modules or embedded in pages/assignments.
- Updates links in Markdown to point to locally downloaded files.
- Avoids duplicate file downloads across the entire scrape.
- Supports various item types including Pages, Files, External URLs, Assignments, Discussions, and Quizzes.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd canvas-scraper
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Access:**
    You need your Canvas instance URL and an API key.
    *   **API URL:** The base URL of your Canvas instance (e.g., `https://harvard.instructure.com`).
    *   **API Key:** Generate this from your Canvas account: Account > Settings > Approved Integrations > +New Access Token.

    You can provide these via:
    *   **Command-line arguments:** `--api-url` and `--api-key`.
    *   **(Optional) Environment variables:** Create a `.env` file in the project root (copy from `.env.example`):
        ```
        CANVAS_API_URL=https://your.canvas.instance.com
        CANVAS_API_KEY=your_api_key_here
        ```
        If using `.env`, uncomment the `python-dotenv` lines in `canvas_scraper.py` and add `python-dotenv` to `requirements.txt`.

## Usage

```bash
python canvas_scraper.py --api-url <YOUR_CANVAS_URL> --api-key <YOUR_API_KEY> [OPTIONS]
```

### Options

- `--course-ids`: Comma-separated list of course IDs to process. If not provided, attempts to process all accessible courses.
- `--output-dir`: Directory to save the downloaded content (default: `canvas_output`).
- `--log-level`: Set the logging level (default: `INFO`). Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

## Output

The scraper will create a directory structure as follows:

```
canvas_output/
└── Course_Name/
    └── Module_Name/
        ├── README.md
        └── _files/
            └── [Downloaded files]
```

Each `README.md` file will contain the module's content, including links to any downloaded files.

## Notes

- Ensure that your API key has the necessary permissions to access the courses and their content.
- The scraper handles various item types, including Pages, Files, External URLs, Assignments, Discussions, and Quizzes, providing a comprehensive overview of the course modules.

## Troubleshooting

If you encounter issues, check the logs for detailed error messages. Ensure that your API credentials are correct and that you have access to the specified courses.
