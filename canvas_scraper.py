#!/usr/bin/env python3
import argparse
import os
import re
import logging
from pathlib import Path

from canvasapi import Canvas
from canvasapi.exceptions import Unauthorized, ResourceDoesNotExist, Forbidden
from canvasapi.course import Course
from canvasapi.module import Module, ModuleItem
from canvasapi.file import File as CanvasFile # Renamed to avoid conflict with open()
from canvasapi.page import Page
from canvasapi.assignment import Assignment

from pathvalidate import sanitize_filename
import html2text # For HTML to Markdown conversion

# --- Environment variables (optional, for convenience) ---
# Consider using python-dotenv to load these from a .env file
# from dotenv import load_dotenv
# load_dotenv()
# CANVAS_API_URL = os.getenv("CANVAS_API_URL")
# CANVAS_API_KEY = os.getenv("CANVAS_API_KEY")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global set to track all downloaded file IDs across the entire run to prevent re-downloads ---
# This could also be scoped per-course if preferred
DOWNLOADED_FILE_IDS_GLOBAL = set()

# --- Helper: HTML to Markdown ---
def convert_html_to_markdown(html_content, base_url_for_images=""):
    """Converts HTML to Markdown using html2text."""
    if not html_content:
        return ""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False # We want to try and preserve image links
    h.body_width = 0 # No wrapping
    # Potentially configure h.baseurl if you can determine it, for relative image paths
    # For now, we'll handle images separately by extracting and re-linking
    markdown_content = h.handle(html_content)
    return markdown_content

# --- Helper: Download a Canvas File Object ---
def download_canvas_file_object(
    canvas_file_obj: CanvasFile,
    target_dir: Path,
    course: Course, # For context if needed for specific file permissions or paths
    canvas: Canvas # Canvas API object
):
    """Downloads a Canvas File object if not already downloaded."""
    if canvas_file_obj.id in DOWNLOADED_FILE_IDS_GLOBAL:
        logger.debug(f"File '{canvas_file_obj.display_name}' (ID: {canvas_file_obj.id}) already processed globally.")
        # Even if downloaded, we still need its local path for linking
        return target_dir / sanitize_filename(canvas_file_obj.display_name)

    sanitized_filename_str = sanitize_filename(canvas_file_obj.display_name)
    file_path = target_dir / sanitized_filename_str
    
    try:
        logger.info(f"Downloading: {canvas_file_obj.display_name} to {file_path}")
        canvas_file_obj.download(str(file_path)) # download method needs a string path
        DOWNLOADED_FILE_IDS_GLOBAL.add(canvas_file_obj.id)
        return file_path
    except Exception as e:
        logger.error(f"Failed to download file {canvas_file_obj.display_name} (ID: {canvas_file_obj.id}): {e}")
        return None


# --- Helper: Extract and Download Embedded Files from HTML ---
def extract_and_download_embedded_files(
    html_content: str,
    files_subdir: Path,
    module_readme_path: Path, # Path to the module's README.md for relative linking
    course: Course,
    canvas: Canvas
):
    """
    Finds Canvas file links in HTML, downloads them, and returns
    a modified HTML string with links updated to relative paths,
    and a list of markdown links for non-image files.
    """
    if not html_content:
        return html_content, []

    modified_html = html_content
    downloaded_item_links_md = [] # For non-image files linked

    # Regex for Canvas file links: /files/(\d+)(?:/download(?:[^\s"]*))?  OR /courses/\d+/files/(\d+)
    # This regex captures the file_id. The ?(?:/download...) part is optional.
    # It also captures links like <img src=".../files/ID/preview...">
    # and <a href=".../files/ID/download?download_frd=1&verifier=...">
    file_id_pattern = re.compile(r'/files/(\d+)(?:/(?:download|preview)[^"\']*)?')
    
    # Create files subdirectory if it doesn't exist
    files_subdir.mkdir(parents=True, exist_ok=True)

    # Find all unique file IDs
    found_file_ids = set(match.group(1) for match in file_id_pattern.finditer(html_content))

    for file_id in found_file_ids:
        try:
            file_id_int = int(file_id)
            if file_id_int in DOWNLOADED_FILE_IDS_GLOBAL:
                # If already downloaded, we still need to rewrite the link
                try:
                    # Attempt to get file object to get its name for the relative path
                    # This might be redundant if we assume a consistent naming scheme
                    canvas_file_obj = course.get_file(file_id_int) # Or canvas.get_file(file_id_int)
                    sanitized_filename_str = sanitize_filename(canvas_file_obj.display_name)
                    local_file_path = files_subdir / sanitized_filename_str
                except ResourceDoesNotExist:
                    logger.warning(f"Could not find file ID {file_id_int} to get name for already downloaded file. Skipping link rewrite for this.")
                    continue

            else: # File not yet downloaded
                canvas_file_obj = course.get_file(file_id_int) # Or canvas.get_file(file_id_int)
                local_file_path = download_canvas_file_object(canvas_file_obj, files_subdir, course, canvas)
                if not local_file_path:
                    continue # Download failed
                sanitized_filename_str = local_file_path.name # Get name from path

            # Path relative to the module's README.md
            relative_path = Path(os.path.relpath(local_file_path, module_readme_path.parent))
            
            # Replace all occurrences of this file_id link in the HTML
            # This is a bit tricky due to various ways links can be formed.
            # We'll replace any link containing /files/FILE_ID... with the new relative path.
            # This might be too broad for complex HTML, but good for a start.
            # A more robust solution might involve HTML parsing (e.g., BeautifulSoup).
            
            # For image tags: update src
            img_pattern = re.compile(rf'(<img[^>]*src=")[^"]*/files/{file_id}(?:/(?:preview|download)[^"\']*)?([^"]*)("[^>]*>)', re.IGNORECASE)
            modified_html = img_pattern.sub(rf'\1{relative_path}\2\3', modified_html)
            
            # For anchor tags: update href and add to markdown list
            # Check if it was an image link already handled
            if not img_pattern.search(html_content): # if it wasn't an image
                link_text_pattern = re.compile(rf'<a[^>]*href="[^"]*/files/{file_id}[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
                match_link_text = link_text_pattern.search(html_content)
                link_text = sanitize_filename(canvas_file_obj.display_name) # Default link text
                if match_link_text:
                    # Try to get a cleaner link text from the anchor
                    temp_text = html2text.html2text(match_link_text.group(1)).strip()
                    if temp_text: link_text = temp_text


                # Update href in the original HTML (might be converted to Markdown later)
                a_pattern = re.compile(rf'(<a[^>]*href=")[^"]*/files/{file_id}(?:/(?:download|preview)[^"\']*)?([^"]*)(")', re.IGNORECASE)
                modified_html = a_pattern.sub(rf'\1{relative_path}\2\3', modified_html)

                # Add a clear markdown link for this file if it's not an image
                downloaded_item_links_md.append(f"* [{link_text}]({relative_path})")


        except ResourceDoesNotExist:
            logger.warning(f"Embedded file ID {file_id} not found in course files. Skipping.")
        except ValueError:
            logger.error(f"Invalid file ID format: {file_id}")
        except Exception as e:
            logger.error(f"Error processing embedded file ID {file_id}: {e}")
            
    return modified_html, list(set(downloaded_item_links_md)) # Remove duplicate links

# --- Main Processing Functions ---
def process_module_item(
    item: ModuleItem,
    module_path: Path,
    course: Course,
    canvas: Canvas
):
    """Processes a single module item and returns its Markdown content and any direct file paths."""
    item_title = sanitize_filename(item.title or f"Untitled_{item.type}_{item.id}")
    logger.info(f"  Processing Item: {item.title} (Type: {item.type})")

    item_md_content = ""
    # Files directly associated with this item, not necessarily embedded in HTML
    # but like a "File" module item.
    associated_files_md_links = [] 

    files_subdir = module_path / "_files" # All files for this module go here
    files_subdir.mkdir(parents=True, exist_ok=True)
    
    module_readme_path = module_path / "README.md" # For relative path calculation

    try:
        if item.type == "Page":
            item_md_content += f"## {item.title}\n\n"
            page: Page = course.get_page(item.page_url) # page_url is the slug
            if page.body:
                # Process embedded files first from original HTML
                processed_html, embedded_file_links_md = extract_and_download_embedded_files(
                    page.body, files_subdir, module_readme_path, course, canvas
                )
                item_md_content += convert_html_to_markdown(processed_html)
                if embedded_file_links_md:
                    item_md_content += "\n\n**Referenced Files:**\n" + "\n".join(embedded_file_links_md)
            else:
                item_md_content += "*(This page has no content)*\n"

        elif item.type == "File":
            canvas_file_obj = course.get_file(item.content_id) # Or canvas.get_file()
            local_file_path = download_canvas_file_object(canvas_file_obj, files_subdir, course, canvas)
            if local_file_path:
                relative_file_path = Path(os.path.relpath(local_file_path, module_readme_path.parent))
                item_md_content += f"* **File:** [{canvas_file_obj.display_name}]({relative_file_path})\n"

        elif item.type == "ExternalUrl":
            item_md_content += f"* **External URL:** [{item.title}]({item.external_url})\n"
        
        elif item.type == "SubHeader":
            item_md_content += f"### {item.title}\n\n"

        elif item.type == "Assignment":
            item_md_content += f"## Assignment: {item.title}\n\n"
            assignment: Assignment = course.get_assignment(item.content_id)
            if assignment.description:
                processed_html, embedded_file_links_md = extract_and_download_embedded_files(
                    assignment.description, files_subdir, module_readme_path, course, canvas
                )
                item_md_content += convert_html_to_markdown(processed_html)
                if embedded_file_links_md:
                    item_md_content += "\n\n**Referenced Files:**\n" + "\n".join(embedded_file_links_md)
            else:
                item_md_content += "*(This assignment has no description)*\n"
            # You could add more assignment details here (due date, points, etc.)
            if assignment.due_at:
                 item_md_content += f"\n*Due: {assignment.due_at_date.strftime('%Y-%m-%d %H:%M %Z')}*\n"
            if hasattr(assignment, 'points_possible') and assignment.points_possible:
                 item_md_content += f"*Points: {assignment.points_possible}*\n"


        elif item.type == "Discussion":
            item_md_content += f"## Discussion: {item.title}\n\n"
            # Discussions are more complex. For now, just link to it.
            # To get content, you'd use course.get_discussion_topic(item.content_id)
            # and then process its 'message' and potentially replies.
            if hasattr(item, 'html_url'):
                 item_md_content += f"*Link to discussion on Canvas: [{item.title}]({item.html_url})*\n"
            else:
                 item_md_content += f"*(Link not available, access through Canvas module)*\n"

        elif item.type == "Quiz":
            item_md_content += f"## Quiz: {item.title}\n\n"
            # Quizzes are also complex.
            if hasattr(item, 'html_url'):
                item_md_content += f"*Link to quiz on Canvas: [{item.title}]({item.html_url})*\n"
            else:
                item_md_content += f"*(Link not available, access through Canvas module)*\n"
            # To get questions: course.get_quiz(item.content_id).get_questions()
            # This would require significant formatting.

        else:
            item_md_content += f"* **{item.type}:** {item.title} "
            if hasattr(item, 'html_url') and item.html_url:
                item_md_content += f" ([View on Canvas]({item.html_url}))"
            item_md_content += "\n"
            logger.warning(f"    Unsupported item type: {item.type} for item '{item.title}'")

    except ResourceDoesNotExist:
        logger.error(f"    Resource for item '{item.title}' (ID: {item.content_id if hasattr(item, 'content_id') else 'N/A'}) not found.")
        item_md_content += f"*Item '{item.title}' could not be retrieved (Resource not found).*\n"
    except Forbidden:
        logger.error(f"    Access forbidden for item '{item.title}' (ID: {item.content_id if hasattr(item, 'content_id') else 'N/A'}).")
        item_md_content += f"*Item '{item.title}' could not be retrieved (Access forbidden).*\n"
    except Exception as e:
        logger.error(f"    Error processing item '{item.title}': {e}", exc_info=True)
        item_md_content += f"*An error occurred while processing item '{item.title}'.*\n"

    return item_md_content + "\n---\n\n" # Add a separator


def process_module(module: Module, course_path: Path, course: Course, canvas: Canvas):
    """Processes a single module, creating its directory and README.md."""
    module_name = sanitize_filename(module.name or f"Untitled_Module_{module.id}")
    logger.info(f"Processing Module: {module.name}")
    module_path = course_path / module_name
    module_path.mkdir(parents=True, exist_ok=True)

    module_readme_content = f"# Module: {module.name}\n\n"
    
    try:
        module_items = module.get_module_items()
    except Exception as e:
        logger.error(f"Could not retrieve items for module '{module.name}': {e}")
        module_readme_content += f"**ERROR: Could not retrieve items for this module.**\n"
        with open(module_path / "README.md", "w", encoding="utf-8") as f:
            f.write(module_readme_content)
        return

    for item in module_items:
        item_md = process_module_item(item, module_path, course, canvas)
        module_readme_content += item_md
    
    # Write the aggregated Markdown for the module
    readme_file_path = module_path / "README.md"
    with open(readme_file_path, "w", encoding="utf-8") as f:
        f.write(module_readme_content)
    logger.info(f"Finished processing module: {module.name}. Content saved to {readme_file_path}")


def process_course(course: Course, output_base_dir: Path, canvas: Canvas):
    """Processes a single course, creating its directory and processing its modules."""
    course_name = sanitize_filename(course.name or f"Untitled_Course_{course.id}")
    logger.info(f"Starting processing for course: {course.name} (ID: {course.id})")
    course_path = output_base_dir / course_name
    course_path.mkdir(parents=True, exist_ok=True)

    # Reset global downloaded files set if you want per-course tracking,
    # otherwise, keep it global to avoid downloads if same file is in multiple courses.
    # For now, we use a truly global set DOWNLOADED_FILE_IDS_GLOBAL.

    try:
        modules = course.get_modules()
        for module in modules:
            module: Module # type hinting
            process_module(module, course_path, course, canvas)
    except Unauthorized:
        logger.error(f"Unauthorized to access modules for course: {course.name}. Skipping.")
    except Forbidden:
        logger.error(f"Forbidden to access modules for course: {course.name}. Check permissions/API key scope. Skipping.")
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing modules for course {course.name}: {e}", exc_info=True)
    
    logger.info(f"Finished processing course: {course.name}")


def main():
    parser = argparse.ArgumentParser(description="Download module content from Canvas courses.")
    parser.add_argument("--api-url", required=not bool(os.getenv("CANVAS_API_URL")), 
                        default=os.getenv("CANVAS_API_URL"),
                        help="URL of the Canvas instance (e.g., https://canvas.instructure.com). Can also be set via CANVAS_API_URL env var.")
    parser.add_argument("--api-key", required=not bool(os.getenv("CANVAS_API_KEY")),
                        default=os.getenv("CANVAS_API_KEY"),
                        help="Canvas API key. Can also be set via CANVAS_API_KEY env var.")
    parser.add_argument("--course-ids",
                        help="Comma-separated list of course IDs to process. If not provided, attempts to process all accessible courses.",
                        default=None)
    parser.add_argument("--output-dir", default="canvas_output",
                        help="Directory to save the downloaded content.")
    parser.add_argument("--log-level", default="INFO", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level.")
    
    args = parser.parse_args()

    logger.setLevel(getattr(logging, args.log_level.upper()))

    if not args.api_url or not args.api_key:
        logger.critical("API URL and API Key are required. Set them via arguments or environment variables.")
        parser.print_help()
        return

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        canvas = Canvas(args.api_url, args.api_key)
        user = canvas.get_current_user()
        logger.info(f"Successfully connected to Canvas as: {user.name}")
    except Unauthorized:
        logger.critical("Canvas API Unauthorized: Invalid API key or URL. Please check your credentials.")
        return
    except Exception as e:
        logger.critical(f"Failed to connect to Canvas: {e}")
        return

    courses_to_process = []
    if args.course_ids:
        ids = [id.strip() for id in args.course_ids.split(',')]
        for course_id in ids:
            if not course_id.isdigit():
                logger.warning(f"Invalid course ID '{course_id}'. Skipping.")
                continue
            try:
                course = canvas.get_course(int(course_id))
                courses_to_process.append(course)
            except ResourceDoesNotExist:
                logger.warning(f"Course with ID {course_id} not found. Skipping.")
            except Exception as e:
                logger.error(f"Error fetching course ID {course_id}: {e}")
    else:
        logger.info("No specific course IDs provided. Fetching all accessible active courses.")
        try:
            # You might want to filter courses (e.g., by enrollment_term_id, or only active enrollments)
            # get_courses() can take parameters like 'enrollment_state': 'active'
            # available_courses = canvas.get_courses(enrollment_state="active")
            available_courses = canvas.get_courses() # Gets all courses the user is associated with
            courses_to_process.extend(available_courses)
        except Exception as e:
            logger.error(f"Error fetching list of all courses: {e}")

    if not courses_to_process:
        logger.info("No courses found to process.")
        return

    for course in courses_to_process:
        try:
            # Check if course object is fully populated (sometimes get_courses gives minimal objects)
            if not hasattr(course, 'name') or course.name is None:
                 full_course = canvas.get_course(course.id) # Fetch full course object
                 process_course(full_course, output_path, canvas)
            else:
                 process_course(course, output_path, canvas)
        except Exception as e:
            logger.error(f"Failed to process course {getattr(course, 'id', 'Unknown ID')}: {e}", exc_info=True)

    logger.info("Canvas scraping process completed.")

if __name__ == "__main__":
    main()
