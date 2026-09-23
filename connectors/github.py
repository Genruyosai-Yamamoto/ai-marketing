import difflib
from connectors.base import BaseConnector
from connectors.github_api import GitHubAPI
from services.connection_service import get_connection
import uuid

class GitHubConnector(BaseConnector):
    def execute(self, action, business_id, user_id, execution_id=None):
        if not execution_id:
            raise ValueError(
                "GitHub execution requires an execution_id"
            )
        if action.get("action_type") != "github":
            raise ValueError(
                "GitHub connector only supports github actions"
            )

        required_fields = {
            "action_title",
            "description",
            "content",
        }

        missing_fields = {
            field
            for field in required_fields
            if not action.get(field)
        }

        if missing_fields:
            raise ValueError(
                "GitHub action is missing required execution fields: "
                f"{sorted(missing_fields)}"
            )
            
        target_path = action.get("target_path")

        if not target_path:
            raise ValueError(
                "GitHub action requires a target_path"
            )

        if target_path.startswith("/"):
            raise ValueError(
                "GitHub target_path must be relative to the repository root"
            )

        if ".." in target_path.split("/"):
            raise ValueError(
                "GitHub target_path cannot contain parent-directory traversal"
            )

        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="github",
        )

        if not connection:
            raise ValueError(
                "GitHub connection not found"
            )

        repository = connection.get("repository")

        if not repository:
            raise ValueError(
                "No GitHub repository selected"
            )

        owner, repo = repository.split("/", 1)

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        github_repo = github.get_repository(
            owner=owner,
            repo=repo,
        )
        
        branch_name = (
            "agent/"
            + action.get("action_title", "github-action")
            .lower()
            .replace(" ", "-")[:30]
            + "-"
            + execution_id[:12]
        )

        branch_result = self.create_action_branch(
            business_id=business_id,
            user_id=user_id,
            branch_name=branch_name,
        )
        
        commit_result = self.update_file_on_branch(
            business_id=business_id,
            user_id=user_id,
            branch_name=branch_result["branch"],
            path=target_path,
            content=action["content"],
            commit_message=action["action_title"],
        )
        
        
    
        return {
            "success": True,
            "status": "github_file_updated",
            "message": (
                "GitHub file updated successfully on the agent branch. "
                "No pull request was created."
            ),
            "business_id": business_id,
            "user_id": user_id,
            "repository": github_repo["full_name"],
            "default_branch": github_repo["default_branch"],
            "target_path": target_path,
            "branch": branch_result,
            "commit": commit_result,
            "action_title": action.get("action_title"),
        }
    
    def create_action_branch( self, business_id, user_id, branch_name,):
        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="github",
        )

        if not connection:
            raise ValueError(
                "GitHub connection not found"
            )

        repository = connection.get("repository")

        if not repository:
            raise ValueError(
                "No GitHub repository selected"
            )

        owner, repo = repository.split("/", 1)

        default_branch = connection.get(
            "default_branch"
        )

        if not default_branch:
            raise ValueError(
                "No default branch configured"
            )

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        base_repository = github.get_repository(
            owner=owner,
            repo=repo,
        )

        if base_repository["default_branch"] != default_branch:
            raise ValueError(
                "Configured default branch does not match "
                "the repository default branch"
            )

        branch_ref = github.get_branch(
            owner=owner,
            repo=repo,
            branch=default_branch,
        )
        
        existing_branch = github.get_branch(
            owner=owner,
            repo=repo,
            branch=branch_name,
        )

        if existing_branch:
            return {
                "success": True,
                "repository": repository,
                "base_branch": default_branch,
                "branch": existing_branch["name"],
                "sha": existing_branch["sha"],
                "already_exists": True,
            }


        branch = github.create_branch(
            owner=owner,
            repo=repo,
            branch_name=branch_name,
            sha=branch_ref["sha"],
        )

        return {
            "success": True,
            "repository": repository,
            "base_branch": default_branch,
            "branch": branch["ref"],
            "sha": branch["sha"],
        }
    def create_change_and_pr( self, business_id, user_id, branch_name, path, content, commit_message, pr_title, pr_body=None,):
        branch_result = self.create_action_branch(
            business_id=business_id,
            user_id=user_id,
            branch_name=branch_name,
        )

        file_result = self.update_file_on_branch(
            business_id=business_id,
            user_id=user_id,
            branch_name=branch_name,
            path=path,
            content=content,
            commit_message=commit_message,
        )

        pr_result = self.create_pull_request(
            business_id=business_id,
            user_id=user_id,
            branch_name=branch_name,
            title=pr_title,
            body=pr_body,
        )
        
        return {
            "success": True,
            "branch": branch_result,
            "file": file_result,
            "pull_request": pr_result,
        }
        
    def update_file_on_branch( self, business_id, user_id, branch_name, path, content, commit_message,):
        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="github",
        )

        if not connection:
            raise ValueError("GitHub connection not found")

        repository = connection.get("repository")
        if not repository:
            raise ValueError("No GitHub repository selected")

        owner, repo = repository.split("/", 1)

        default_branch = connection.get("default_branch")
        if not default_branch:
            raise ValueError("No default branch configured")

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        github_repo = github.get_repository(
            owner=owner,
            repo=repo,
        )

        if github_repo["default_branch"] != default_branch:
            raise ValueError(
                "Configured default branch does not match "
                "the repository default branch"
            )

        file_data = github.get_file(
            owner=owner,
            repo=repo,
            path=path,
            ref=branch_name,
        )
        
        import base64

        existing_content = base64.b64decode(
            file_data["content"]
        ).decode("utf-8")

        existing_line_count = len(existing_content.splitlines())
        new_line_count = len(content.splitlines())
        diff = list(
            difflib.unified_diff(
                existing_content.splitlines(),
                content.splitlines(),
                lineterm="",
            )
        )

        deleted_line_count = sum(
            1
            for line in diff
            if line.startswith("-") and not line.startswith("---")
        )

        if existing_line_count >= 20:
            line_ratio = new_line_count / existing_line_count

            if line_ratio < 0.25:
                raise ValueError(
                    "Refusing potentially destructive file replacement: "
                    f"existing file has {existing_line_count} lines, "
                    f"new content has {new_line_count} lines "
                    f"({line_ratio:.1%} of the original)"
                )
        deletion_ratio = (
            deleted_line_count / existing_line_count
            if existing_line_count
            else 0
        )

        if existing_line_count >= 20 and deletion_ratio > 0.50:
            raise ValueError(
                "Refusing potentially destructive file replacement: "
                f"{deleted_line_count} of {existing_line_count} lines "
                f"would be deleted ({deletion_ratio:.1%})"
            )

        result = github.update_file(
            owner=owner,
            repo=repo,
            path=path,
            content=content,
            message=commit_message,
            branch=branch_name,
            sha=file_data["sha"],
        )

        return {
            "success": True,
            "repository": repository,
            "branch": branch_name,
            "path": path,
            "commit_sha": result["commit_sha"],
            "content_sha": result["content_sha"],
        }
    def create_pull_request(self,business_id,user_id,branch_name,title,body=None,):
        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="github",
        )

        if not connection:
            raise ValueError("GitHub connection not found")

        repository = connection.get("repository")
        if not repository:
            raise ValueError("No GitHub repository selected")

        owner, repo = repository.split("/", 1)

        default_branch = connection.get("default_branch")
        if not default_branch:
            raise ValueError("No default branch configured")

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        github_repo = github.get_repository(
            owner=owner,
            repo=repo,
        )

        if github_repo["default_branch"] != default_branch:
            raise ValueError(
                "Configured default branch does not match "
                "the repository default branch"
            )
            
        existing_prs = github.list_pull_requests(
            owner=owner,
            repo=repo,
            head=f"{owner}:{branch_name}",
            base=default_branch,
            state="open",
        )

        if existing_prs:
            existing_pr = existing_prs[0]

            return {
                "success": True,
                "repository": repository,
                "number": existing_pr["number"],
                "url": existing_pr["url"],
                "state": existing_pr["state"],
                "head": existing_pr["head"],
                "base": existing_pr["base"],
                "already_exists": True,
            }

        result = github.create_pull_request(
            owner=owner,
            repo=repo,
            title=title,
            head=branch_name,
            base=default_branch,
            body=body,
        )

        return {
            "success": True,
            "repository": repository,
            "number": result["number"],
            "url": result["url"],
            "state": result["state"],
            "head": result["head"],
            "base": result["base"],
        }
    def find_pull_request( self, business_id, user_id, branch_name,):
        connection = get_connection(
            business_id=business_id,
            user_id=user_id,
            provider="github",
        )

        if not connection:
            raise ValueError("GitHub connection not found")

        repository = connection.get("repository")
        if not repository:
            raise ValueError("No GitHub repository selected")

        owner, repo = repository.split("/", 1)

        default_branch = connection.get("default_branch")
        if not default_branch:
            raise ValueError("No default branch configured")

        github = GitHubAPI(
            access_token=connection["access_token"]
        )

        github_repo = github.get_repository(
            owner=owner,
            repo=repo,
        )

        if github_repo["default_branch"] != default_branch:
            raise ValueError(
                "Configured default branch does not match "
                "the repository default branch"
            )

        pull_requests = github.list_pull_requests(
            owner=owner,
            repo=repo,
            head=f"{owner}:{branch_name}",
            base=default_branch,
            state="open",
        )

        return {
            "success": True,
            "repository": repository,
            "pull_request": pull_requests[0] if pull_requests else None,
        }