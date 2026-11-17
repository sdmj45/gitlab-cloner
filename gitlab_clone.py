import base64
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import gitlab
from gitlab.exceptions import GitlabError, GitlabParsingError

MAIN_GROUP_ID = "GROUP_ID"

# Use the GitLab instance root URL, NOT a subgroup/project URL.
# Examples:
#   https://gitlab.com
#   https://gitlab.company.com
GITLAB_URL = ""

PRIVATE_TOKEN = "YOUR PAT OR GROUP ACCESS TOKEN"
DIST_DIR = Path("dist")

def normalize_gitlab_url(url):
    """Remove accidental trailing slash or /api/v4 from the configured URL."""
    url = url.strip().rstrip("/")
    if url.endswith("/api/v4"):
        url = url[:-7].rstrip("/")
    return url


def validate_configuration():
    if not MAIN_GROUP_ID or MAIN_GROUP_ID == "YOUR_MAIN_GROUP_ID":
        raise ValueError("Set MAIN_GROUP_ID to your GitLab group ID or URL-encoded group path.")

    if not GITLAB_URL or GITLAB_URL == "YOUR_GITLAB_URL":
        raise ValueError("Set GITLAB_URL to your GitLab instance root URL.")

    if not PRIVATE_TOKEN :
        raise ValueError(
            "Set PRIVATE_TOKEN in the script or define the GITLAB_TOKEN environment variable."
        )

    parsed = urlparse(GITLAB_URL)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("GITLAB_URL must be a valid http:// or https:// URL.")


def make_gitlab_client():
    url = normalize_gitlab_url(GITLAB_URL)
    gl = gitlab.Gitlab(url, private_token=PRIVATE_TOKEN, timeout=30)
    gl.auth()  # Validate the token and API connection.
    return gl


def get_group(gl, group_id):
    # GitLab accepts either a numeric group ID or a URL-encoded full group path.
    return gl.groups.get(str(group_id))


def get_all_projects(gl, group):
    """Collect projects recursively, avoiding duplicate projects."""
    projects_by_id = {}

    for project in group.projects.list(
        include_subgroups=False,
        get_all=True,
    ):
        projects_by_id[project.id] = project

    for subgroup in group.subgroups.list(get_all=True):
        subgroup_details = gl.groups.get(subgroup.id)
        for project in get_all_projects(gl, subgroup_details):
            projects_by_id[project.id] = project

    return list(projects_by_id.values())


def clone_project(project, destination):
    destination = Path(destination)

    if destination.exists() and any(destination.iterdir()):
        print(f"SKIP: {project.path_with_namespace} (destination is not empty)")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Use a temporary Git config environment variable for authentication.
    # This avoids putting the access token in the clone URL or command line.
    credentials = f"oauth2:{PRIVATE_TOKEN}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("ascii")

    env = os.environ.copy()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
    env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {basic_auth}"

    print(f"Cloning: {project.path_with_namespace}")
    try:
        subprocess.run(
            ["git", "clone", project.http_url_to_repo, str(destination)],
            check=True,
            env=env,
        )
        print(f"SUCCESS: {project.path_with_namespace}")
    except subprocess.CalledProcessError as exc:
        print(f"FAILED: {project.path_with_namespace} (git exit code {exc.returncode})")
        if destination.exists() and not any(destination.iterdir()):
            destination.rmdir()


def main():
    validate_configuration()

    print("Connecting to GitLab...")
    gl = make_gitlab_client()
    print("Connected successfully.")

    print(f"Fetching group: {MAIN_GROUP_ID}")
    main_group = get_group(gl, MAIN_GROUP_ID)

    projects = get_all_projects(gl, main_group)
    print(f"Found {len(projects)} project(s).")

    for project_summary in projects:
        # Fetch the full project object to ensure the clone URL is available.
        project = gl.projects.get(project_summary.id)
        destination = DIST_DIR / project.path_with_namespace
        clone_project(project, destination)

    print("Finished processing all projects.")


if __name__ == "__main__":
    try:
        main()
    except GitlabParsingError as exc:
        print("\nGitLab returned a response that python-gitlab could not parse.")
        print("Check that GITLAB_URL is only the instance root, for example:")
        print("  https://gitlab.com")
        print("  https://gitlab.company.com")
        print("Do NOT include /api/v4/groups/... or a project/group path.")
        print(f"Details: {exc}")
        sys.exit(1)
    except GitlabError as exc:
        print(f"\nGitLab API error: {exc}")
        print("Check the token, its scopes, group access, and group ID.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)
