"""jobu CLI"""

import argparse
import io
import os
import sys
import urllib.request
import zipfile


GITHUB_REPO = "dok9gold/jobu"


def download_template(branch: str, dest_path: str) -> None:
    """GitHub에서 브랜치 다운로드"""
    url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/{branch}.zip"

    print(f"Downloading template from '{branch}' branch...")

    try:
        with urllib.request.urlopen(url) as response:
            zip_data = response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Error: Template '{branch}' not found")
            sys.exit(1)
        raise

    # zip 압축 해제
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        # jobu-{branch}/ 형태로 압축되어 있음
        prefix = zf.namelist()[0].split('/')[0]

        for member in zf.namelist():
            # 첫 번째 디렉토리 제거하고 추출
            relative_path = member[len(prefix) + 1:]
            if not relative_path:
                continue

            target_path = os.path.join(dest_path, relative_path)

            if member.endswith('/'):
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(member) as src, open(target_path, 'wb') as dst:
                    dst.write(src.read())


def init_project(project_name: str, template: str) -> None:
    """프로젝트 초기화"""
    project_path = os.path.join(os.getcwd(), project_name)

    if os.path.exists(project_path):
        print(f"Error: '{project_name}' already exists")
        sys.exit(1)

    os.makedirs(project_path)

    download_template(template, project_path)

    print(f"Created project '{project_name}' from template '{template}'")
    print()
    print("Next steps:")
    print(f"  cd {project_name}")
    print("  python -m venv .venv")
    print("  source .venv/bin/activate")
    print("  pip install -r requirements.txt")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jobu",
        description="jobu - Python 기반 통합 배치 스케줄링 시스템"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new jobu project")
    init_parser.add_argument("project_name", help="Project name")
    init_parser.add_argument(
        "-t", "--template",
        default="main",
        help="Template branch name (default: main)"
    )

    # version
    parser.add_argument("-v", "--version", action="version", version="%(prog)s 0.2.0")

    args = parser.parse_args()

    if args.command == "init":
        init_project(args.project_name, args.template)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
