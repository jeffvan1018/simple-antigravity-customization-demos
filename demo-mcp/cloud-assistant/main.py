from fastmcp import FastMCP

mcp = FastMCP("Cloud Assistant")

@mcp.tool
def get_cloud_projects() -> list[str]:
    """Return a hardcoded list of cloud project names."""
    return [
        "project-alpha",
        "project-beta",
        "project-gamma",
    ]

