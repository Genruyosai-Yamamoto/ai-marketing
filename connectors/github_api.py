import requests


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"


class GitHubAPIError(Exception):
    """Raised when the GitHub API returns an error."""
    pass


class GitHubAPI:
    def __init__(self, access_token):
        if not access_token:
            raise ValueError("GitHub access token is required")

        self.base_url = GITHUB_API_BASE_URL
        self.access_token = access_token

    @property
    def headers(self):
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.access_token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        
    def get_authenticated_user(self):
        response = requests.get(
            f"{self.base_url}/user",
            headers=self.headers,
            timeout=10,
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub authenticated user lookup failed: "
                f"{response.status_code}"
            )

        data = response.json()

        return {
            "id": data.get("id"),
            "login": data.get("login"),
            "name": data.get("name"),
            "email": data.get("email"),
        }
        
    def get_repository(self, owner, repo):
        response = requests.get(
            f"{self.base_url}/repos/{owner}/{repo}",
            headers=self.headers,
            timeout=10,
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub repository lookup failed: "
                f"{response.status_code}"
            )

        data = response.json()

        return {
            "id": data.get("id"),
            "full_name": data.get("full_name"),
            "default_branch": data.get("default_branch"),
            "private": data.get("private"),
        }
        
        def create_branch(self, owner, repo, branch_name, sha):
            response = requests.post(
                f"{self.base_url}/repos/{owner}/{repo}/git/refs",
                headers=self.headers,
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": sha,
                },
                timeout=10,
            )

            if not response.ok:
                raise GitHubAPIError(
                    f"GitHub branch creation failed: {response.status_code}"
                )

            data = response.json()

            return {
                "ref": data.get("ref"),
                "sha": data.get("object", {}).get("sha"),
            }
        
        def get_file(self, owner, repo, path, ref=None):
            params = {}

            if ref:
                params["ref"] = ref

            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                headers=self.headers,
                params=params,
                timeout=10,
            )

            if not response.ok:
                raise GitHubAPIError(
                    f"GitHub file lookup failed: {response.status_code}"
                )

            data = response.json()

            return {
                "name": data.get("name"),
                "path": data.get("path"),
                "sha": data.get("sha"),
                "content": data.get("content"),
                "encoding": data.get("encoding"),
                "download_url": data.get("download_url"),
            }
        
        def update_file(
        self,
        owner,
        repo,
        path,
        content,
        message,
        branch,
        sha=None,
    ):
            import base64

            encoded_content = base64.b64encode(
                content.encode("utf-8")
            ).decode("utf-8")

            payload = {
                "message": message,
                "content": encoded_content,
                "branch": branch,
            }

            if sha:
                payload["sha"] = sha

            response = requests.put(
                f"{self.base_url}/repos/{owner}/{repo}/contents/{path}",
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            if not response.ok:
                raise GitHubAPIError(
                    f"GitHub file update failed: {response.status_code}"
                )

            data = response.json()

            return {
                "commit_sha": data.get("commit", {}).get("sha"),
                "content_sha": data.get("content", {}).get("sha"),
                "path": data.get("content", {}).get("path"),
            }
        
        def create_pull_request(
        self,
        owner,
        repo,
        title,
        head,
        base,
        body=None,
    ):
            payload = {
                "title": title,
                "head": head,
                "base": base,
            }

            if body:
                payload["body"] = body

            response = requests.post(
                f"{self.base_url}/repos/{owner}/{repo}/pulls",
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            if not response.ok:
                raise GitHubAPIError(
                    f"GitHub pull request creation failed: {response.status_code}"
                )

            data = response.json()

            return {
                "number": data.get("number"),
                "url": data.get("html_url"),
                "state": data.get("state"),
                "head": data.get("head", {}).get("ref"),
                "base": data.get("base", {}).get("ref"),
            }