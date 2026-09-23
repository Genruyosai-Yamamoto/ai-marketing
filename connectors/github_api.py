import requests
import os
from dotenv import load_dotenv
load_dotenv()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")

GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
print(
    "DEBUG GitHub OAuth config:",
    {
        "client_id": GITHUB_CLIENT_ID,
        "client_id_length": len(GITHUB_CLIENT_ID) if GITHUB_CLIENT_ID else 0,
        "redirect_uri": GITHUB_REDIRECT_URI,
    },
)

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
        
    @staticmethod
    def get_authorization_url(state):
        if not GITHUB_CLIENT_ID:
            raise ValueError("GITHUB_CLIENT_ID is not configured")

        from urllib.parse import urlencode

        params = {
            "client_id": GITHUB_CLIENT_ID,
            "redirect_uri": GITHUB_REDIRECT_URI,
            "scope": "repo",
            "state": state,
        }

        authorization_url = (
            "https://github.com/login/oauth/authorize?"
            + urlencode(params)
        )

        print(
            "DEBUG GitHub OAuth authorization URL:",
            {
                "client_id": GITHUB_CLIENT_ID,
                "redirect_uri": GITHUB_REDIRECT_URI,
                "state_present": bool(state),
                "url": authorization_url,
            },
        )

        return authorization_url
        
    @staticmethod
    def exchange_code_for_token(code):
        if not GITHUB_CLIENT_ID:
            raise ValueError("GITHUB_CLIENT_ID is not configured")

        if not GITHUB_CLIENT_SECRET:
            raise ValueError("GITHUB_CLIENT_SECRET is not configured")

        response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        print(
            "DEBUG GitHub OAuth POST payload:",
            {
                "client_id": GITHUB_CLIENT_ID[:6] + "..." if GITHUB_CLIENT_ID else None,
                "client_secret_length": len(GITHUB_CLIENT_SECRET) if GITHUB_CLIENT_SECRET else 0,
                "code_length": len(code) if code else 0,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
        )
        print(
            "DEBUG GitHub OAuth request data:",
            {
                "client_id_present": bool(GITHUB_CLIENT_ID),
                "client_secret_present": bool(GITHUB_CLIENT_SECRET),
                "code_present": bool(code),
                "redirect_uri": GITHUB_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        print(
            "DEBUG GitHub OAuth exchange:",
            {
                "status_code": response.status_code,
                "url": response.url,
                "history": [
                    {
                        "status_code": r.status_code,
                        "url": r.url,
                        "location": r.headers.get("Location"),
                    }
                    for r in response.history
                ],
                "content_type": response.headers.get("Content-Type"),
            },
        )
        print(
            "DEBUG GitHub OAuth response headers:",
            {
                "server": response.headers.get("Server"),
                "x_github_request_id": response.headers.get("X-GitHub-Request-Id"),
                "via": response.headers.get("Via"),
                "content_length": response.headers.get("Content-Length"),
                "cache_control": response.headers.get("Cache-Control"),
            },
        )

        print(
            "DEBUG GitHub OAuth request:",
            {
                "method": response.request.method,
                "url": response.request.url,
                "host": response.request.headers.get("Host"),
            },
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub OAuth token exchange failed: "
                f"{response.status_code}"
            )

        data = response.json()
        print(
            "DEBUG GitHub OAuth response body:",
            {
                "has_access_token": "access_token" in data,
                "has_login": "login" in data,
                "has_id": "id" in data,
                "keys": list(data.keys()),
            },
        )

        if "error" in data:
            raise GitHubAPIError(
                data.get("error_description")
                or data.get("error")
                or "GitHub OAuth token exchange failed"
            )

        access_token = data.get("access_token")
        print(
            "DEBUG GitHub OAuth token metadata:",
            {
                "token_type": data.get("token_type"),
                "scope": data.get("scope"),
                "expires_in": data.get("expires_in"),
                "refresh_token_present": bool(data.get("refresh_token")),
                "access_token_present": bool(access_token),
            },
        )

        if not access_token:
            raise GitHubAPIError(
                "GitHub OAuth response did not contain an access token"
            )

        return {
            "access_token": access_token,
            "token_type": data.get("token_type"),
            "scope": data.get("scope"),
        }
        
    def get_authenticated_user(self):
        response = requests.get(
            f"{self.base_url}/user",
            headers=self.headers,
            timeout=10,
        )
        print(
            "DEBUG GitHub /user:",
            {
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type"),
                "response_keys": (
                    list(response.json().keys())
                    if response.headers.get("Content-Type", "").startswith("application/json")
                    else None
                ),
            },
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub authenticated user lookup failed: "
                f"{response.status_code}"
            )

        data = response.json()
        print(
            "DEBUG GitHub OAuth token response keys:",
            list(data.keys()),
        )
        return {
            "id": data.get("id"),
            "login": data.get("login"),
            "name": data.get("name"),
            "email": data.get("email"),
        }
        
    def list_repositories(self):
        response = requests.get(
            f"{self.base_url}/user/repos",
            headers=self.headers,
            params={
                "per_page": 100,
                "sort": "updated",
                "direction": "desc",
            },
            timeout=10,
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub repository listing failed: {response.status_code}"
            )

        repositories = response.json()

        return [
            {
                "id": repo.get("id"),
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "private": repo.get("private"),
                "default_branch": repo.get("default_branch"),
                "html_url": repo.get("html_url"),
            }
            for repo in repositories
        ]
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
        
    def update_file( self, owner, repo, path, content, message, branch, sha=None,):
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
        
    def create_pull_request( self, owner, repo, title, head, base, body=None,):
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
        
    def get_branch(self, owner, repo, branch):
        response = requests.get(
            f"{self.base_url}/repos/{owner}/{repo}/branches/{branch}",
            headers=self.headers,
            timeout=10,
        )

        if response.status_code == 404:
            return None

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub branch lookup failed: {response.status_code}"
            )

        data = response.json()

        return {
            "name": data.get("name"),
            "sha": data.get("commit", {}).get("sha"),
            "protected": data.get("protected"),
        }
        
    def get_repository_tree( self, owner, repo, sha, ):
        response = requests.get(
            f"{self.base_url}/repos/{owner}/{repo}/git/trees/{sha}",
            headers=self.headers,
            params={
                "recursive": "1",
            },
            timeout=10,
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub repository tree lookup failed: "
                f"{response.status_code}"
            )

        data = response.json()

        return {
            "sha": data.get("sha"),
            "truncated": data.get("truncated"),
            "tree": [
                {
                    "path": item.get("path"),
                    "mode": item.get("mode"),
                    "type": item.get("type"),
                    "sha": item.get("sha"),
                    "size": item.get("size"),
                }
                for item in data.get("tree", [])
            ],
        }
    def list_pull_requests( self, owner, repo, head=None, base=None, state="open",):
        params = {
            "state": state,
            "per_page": 100,
        }

        if head:
            params["head"] = head

        if base:
            params["base"] = base

        response = requests.get(
            f"{self.base_url}/repos/{owner}/{repo}/pulls",
            headers=self.headers,
            params=params,
            timeout=10,
        )

        if not response.ok:
            raise GitHubAPIError(
                f"GitHub pull request listing failed: {response.status_code}"
            )

        return [
            {
                "number": pr.get("number"),
                "url": pr.get("html_url"),
                "state": pr.get("state"),
                "head": pr.get("head", {}).get("ref"),
                "base": pr.get("base", {}).get("ref"),
                "title": pr.get("title"),
            }
            for pr in response.json()
        ]
        