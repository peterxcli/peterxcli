import os
import sys
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import requests
from tqdm import tqdm


def generate_contribution_histogram(username: str, repo_owner: str, repo_name: str):
    """
    Generate a contribution histogram for a user's PRs in a specific repository.

    Args:
        username (str): GitHub username to analyze
        repo_owner (str): Owner of the repository
        repo_name (str): Name of the repository
    """
    # GitHub API setup
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN environment variable is not set")

    HEADERS = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    def run_graphql_query(query, variables=None):
        response = requests.post(
            "https://api.github.com/graphql",
            headers=HEADERS,
            json={"query": query, "variables": variables},
        )
        if response.status_code != 200:
            raise Exception(f"Query failed: {response.status_code} - {response.text}")
        return response.json()

    def get_month_year(date_str):
        # Handle both formats: with and without timezone
        if "+" in date_str:
            date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
        else:
            date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return date.strftime("%Y-%m")

    def fetch_prs_with_cursor(query, variables, desc):
        prs = []
        has_next_page = True
        end_cursor = None

        with tqdm(desc=desc) as pbar:
            while has_next_page:
                variables["cursor"] = end_cursor
                result = run_graphql_query(query, variables)

                if "errors" in result:
                    raise Exception(f"GraphQL Error: {result['errors']}")

                prs_data = result["data"]["search"]["edges"]
                prs.extend([edge["node"] for edge in prs_data])

                page_info = result["data"]["search"]["pageInfo"]
                has_next_page = page_info["hasNextPage"]
                end_cursor = page_info["endCursor"]

                pbar.update(len(prs_data))

        return prs

    # GraphQL query template
    prs_query = """
    query($cursor: String, $searchQuery: String!) {
      search(
        query: $searchQuery
        type: ISSUE
        first: 100
        after: $cursor
      ) {
        edges {
          node {
            ... on PullRequest {
              createdAt
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    # Fetch authored PRs
    print(f"Fetching PRs authored by {username}...")
    authored_variables = {
        "searchQuery": f"repo:{repo_owner}/{repo_name} is:pr author:{username}"
    }
    authored_prs = fetch_prs_with_cursor(
        prs_query, authored_variables, "Fetching authored PRs"
    )
    authored_dates = [get_month_year(pr["createdAt"]) for pr in authored_prs]

    # Fetch reviewed PRs
    print(f"\nFetching PRs reviewed by {username}...")
    reviewed_variables = {
        "searchQuery": f"repo:{repo_owner}/{repo_name} is:pr reviewed-by:{username}"
    }
    reviewed_prs = fetch_prs_with_cursor(
        prs_query, reviewed_variables, "Fetching reviewed PRs"
    )
    reviewed_dates = [get_month_year(pr["createdAt"]) for pr in reviewed_prs]

    # Create DataFrames for counting
    authored_df = (
        pd.DataFrame(authored_dates, columns=["month"])
        .groupby("month")
        .size()
        .reset_index(name="authored_count")
    )
    reviewed_df = (
        pd.DataFrame(reviewed_dates, columns=["month"])
        .groupby("month")
        .size()
        .reset_index(name="reviewed_count")
    )

    # Merge DataFrames
    merged_df = pd.merge(authored_df, reviewed_df, on="month", how="outer").fillna(0)
    merged_df["month"] = pd.to_datetime(merged_df["month"], format="%Y-%m")
    merged_df = merged_df.sort_values("month")

    # Plot histogram
    plt.figure(figsize=(12, 6))
    bar_width = 0.35
    x = range(len(merged_df["month"]))

    # Calculate totals
    total_authored = int(sum(merged_df["authored_count"]))
    total_reviewed = int(sum(merged_df["reviewed_count"]))

    # Plot bars
    plt.bar(
        [i - bar_width / 2 for i in x],
        merged_df["authored_count"],
        bar_width,
        label=f"PRs Authored (Total: {total_authored:,})",
        color="skyblue",
    )
    plt.bar(
        [i + bar_width / 2 for i in x],
        merged_df["reviewed_count"],
        bar_width,
        label=f"PRs Reviewed (Total: {total_reviewed:,})",
        color="lightcoral",
    )

    # Add total annotations
    plt.annotate(
        f"Total Authored: {total_authored:,}",
        xy=(0.02, 0.95),
        xycoords="axes fraction",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="skyblue", alpha=0.3),
    )
    plt.annotate(
        f"Total Reviewed: {total_reviewed:,}",
        xy=(0.02, 0.90),
        xycoords="axes fraction",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="lightcoral", alpha=0.3),
    )

    plt.xlabel("Month")
    plt.ylabel("Number of Pull Requests")
    plt.title(f"Contribution History of {username} in {repo_owner}/{repo_name}")
    plt.xticks(x, merged_df["month"].dt.strftime("%Y-%m"), rotation=45)
    plt.legend()
    plt.tight_layout()

    # Save the plot
    output_filename = f"{username}-{repo_owner}-{repo_name}-contribution-histogram.png"
    plt.savefig(output_filename)
    print(f"\nContribution histogram saved as: {output_filename}")


# example: python oss-contribution.py peterxcli,apache/ozone peterxcli,apache/kafka
if __name__ == "__main__":
    # read all arguments
    usernames = []
    repos = []
    for arg in sys.argv[1:]:
        username, repo = arg.split(",")
        usernames.append(username)
        repo_owner, repo_name = repo.split("/")
        repos.append((repo_owner, repo_name))

    for username, repo in zip(usernames, repos):
        generate_contribution_histogram(username, repo[0], repo[1])
