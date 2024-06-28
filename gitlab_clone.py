import os
import subprocess
import gitlab
from gitlab.v4.objects.groups import Group

# Configuration for GitLab

MAIN_GROUP_ID = 'YOUR_MAIN_GROUP_ID'
GITLAB_URL = 'YOUR_GITLAB_URL'
PRIVATE_TOKEN = 'YOUR_PRIVATE_TOKEN'
DIST_DIR = 'dist'

# Initialize GitLab connection
gl = gitlab.Gitlab(GITLAB_URL, private_token=PRIVATE_TOKEN)

def get_group(group_id):
    return gl.groups.get(group_id)

def get_all_projects(group):
    all_projects = []
    projects = group.projects.list(include_subgroups=True, all=True)
    all_projects.extend(projects)
    
    subgroups = group.subgroups.list(all=True)
    for subgroup in subgroups:
        subgroup_details = gl.groups.get(subgroup.id)
        all_projects.extend(get_all_projects(subgroup_details))
    
    return all_projects

def create_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)

def clone_project(project, directory):
    if not os.listdir(directory):  # Check if directory is empty
        print(f"Cloning {project.name} into {directory}...")
        print(f"Using URL: {project.http_url_to_repo}")
        try:
            subprocess.run(['git', 'clone', project.http_url_to_repo, directory], check=True)
            print(f"Finished cloning {project.name}.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to clone {project.name}: {e}")
    else:
        print(f"Directory {directory} already exists and is not empty. Skipping clone.")

def main():
    # Get the main group
    main_group = get_group(MAIN_GROUP_ID)
    
    # Get all projects in the main group and its subgroups
    projects = get_all_projects(main_group)
    
    for project in projects:
        # Create full directory path for each project, including subgroup directories
        project_path = project.path_with_namespace
        local_directory = os.path.join(DIST_DIR, project_path)
        
        # Create the necessary directories
        create_directory(local_directory)
        
        # Clone the project
        clone_project(project, local_directory)

if __name__ == "__main__":
    main()