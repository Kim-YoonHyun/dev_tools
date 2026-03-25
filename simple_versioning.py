import sys
import os
import copy

import json
import argparse

from datetime import datetime
from pathlib import Path


USER_PATH = Path("~").expanduser()
sys.path.insert(0, str(USER_PATH / "library" / "dev_tools")) 
sys.path.insert(0, str(USER_PATH / "library" / "utilskit" / "src"))
sys.path.insert(0, str(USER_PATH / "library" / "logie" / "src"))
from utilskit.timeutils import get_now
from utilskit.versionutils import version_up, git_addcommit
from logie.docsutils import log2donelog, documenting, tmp2new, delete_tmp


# [0.0.1] @done_log: GitPython 활용에 맞춰서 버저닝 구조 대폭 변경
def versioning(tools_path, save, dev):
    if dev:
        from beta import utils as u
    else:
        import utils as u

    # from utilskit import versionutils as vu
    from utilskit import versionutils as vu
    import fnmatch
    import logie as lo

    # tools_path = Path(__file__).resolve().parent
    with open(Path(tools_path) / "version_dict.json", "r", encoding="utf-8-sig") as f:
        version_dict = json.load(f)

    valid_file_list = list(version_dict.keys())
    git_modi_list = vu.get_git_modified(tools_path, tools_path)

    # 컴포넌트별 git status 추출(신규)
    git_new_list = vu.get_git_new(tools_path, tools_path)
    git_check_list = git_modi_list + git_new_list

    for git_check in git_check_list:
        file_path = git_check["file_path"]
        name = file_path.split('/')[-1]

        if name not in valid_file_list:
            continue
        pre_version = version_dict[name]
        # status = git_check["status"]
        log_list = lo.extract_log(file_path)
        comment_log = "\n- ".join(log_list)
        comment_log = "- " + comment_log

        # 
        new_version = u.simple_documenting(name, comment_log, pre_version)
        version_dict[name] = new_version

        # 각 대상 파일 별 @log 를 @done_log 로 변경
        if save:
            try:
                log2donelog(file_path, new_version)
            except FileNotFoundError:
                pass
        else:
            print(f"|예정| {file_path} 의 주석을 done 으로 변경")


    if save:
        # .tmp 를 원본으로 교체
        do = tmp2new(tools_path)
        # [0.1.0] @done_log: version dict 저장되도록 수정
        with open(Path(tools_path) / "version_dict.json", "w", encoding="utf-8-sig") as f:
            json.dump(version_dict, f, indent="\t", ensure_ascii=False)

        if do == 1:
            # git add & commit 진행
            git_addcommit(tools_path, f'*upload: {get_now("년-월-일")}')

            # # archiving
            # u.archiving(
            #     archive_path=archive_path, 
            #     lock_info=lock_info
            # )
        if do == 0:
            delete_tmp(tools_path)
    else:
        print(f"|예정| release.md.tmp 생성")
        print(f"|예정| pyproject.toml.tmp 생성")
        print(f"|예정| .hash_cache.json.tmp 생성")
        print(f'|예정| *upload: {get_now("년-월-일")} 으로 커밋')
        print(f"|예정| 대상 컴포넌트 전체 아카이브 파일 생성")
    sys.exit()


# [0.0.1] @done_log: dev_tools 에서 versioning 을 통해 각 패키지의 버저닝을 진행
# [0.0.1] @done_log: versioning 실행시 exit code를 받을 수 있도록 기본값을 가진 check_only 인자를 추가
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    save = args.save
    dev = args.dev

    # 경로설정
    tools_path = str(Path(__file__).resolve().parent)
    
    # 진행
    try:
        versioning(tools_path, save, dev)
    except KeyboardInterrupt:
        delete_tmp(tools_path)
    
    # retuncode 를 0 으로 설정(build 시 검증용)
    sys.exit(0)

if __name__ == "__main__":
    main()

