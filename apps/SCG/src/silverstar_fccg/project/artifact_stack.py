"""Read task and reviewed MSP bounds tied to actual artifacts, never hardware measurements."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from silverstar_fccg.core.workspace import WorkspacePolicy, WorkspacePolicyError
from silverstar_fccg.project.stack_manifest import Manifest_Load


_PREFIX = "artifact_stack_v1="
_ANALYSIS_TOOLS = {'stack_arm.py', 'stack_runtime.py', 'stack_review.py',
                   'software_stack_inputs.json', 'software_stack_review.md'}
_MSP_FIELDS = ('configured_bytes', 'main_reset_bytes', 'priority_levels', 'priority_bits',
               'exception_frame_bytes', 'maximum_configurable_handler_bytes',
               'fixed_handler_bytes', 'worst_known_bytes', 'margin_bytes', 'passes')


def ArtifactStackReportSummary_Encode(output: str, expected_root: Path) -> str:
    paths = re.findall(r"^FIRMWARE_STACK_REPORT\|(.+)$", output, re.MULTILINE)
    if len(paths) != 1:
        return ""
    try:
        path = Path(paths[0].strip())
        if not path.is_absolute() or path.stat().st_size > 4 * 1024 * 1024:
            return ""
        raw = path.read_bytes()
        report = json.loads(raw)
        if report["schema"] != "silverstar.stack-budget/1":
            return ""
        relative = PurePosixPath(report["elf"].replace("\\", "/"))
        if (relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2 or
                relative.suffix != '.elf' or report['configuration'] not in {'Release', 'Debug'} or
                relative.parent.name != report['configuration']):
            return ""
        root = path.parents[len(relative.parts) - 1]
        if root.absolute() != Path(expected_root).absolute():
            return ""
        policy = WorkspacePolicy(root)
        if policy.Path_Resolve(relative.parent / "stack-budget.json", allow_root=False) != path.absolute():
            return ""
        artifacts = {}
        for name, relative_path in (("elf", relative), ("checker", "Tools/check_task_stacks.py")):
            artifact_path = policy.Path_Resolve(relative_path, allow_root=False)
            with artifact_path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != report[name + "_sha256"]:
                return ""
            artifacts[name] = {"path": str(artifact_path), "sha256": digest}
        value = {key: report[key] for key in ("configuration", "compiler", "minimum_margin_bytes",
                 "tasks", "checks", "passes", "whole_program_stack_acceptance")}
        if report['whole_program_stack_acceptance'] in ('SOFTWARE BOUND PASS', 'SOFTWARE BOUND FAIL'):
            hashes = report['analysis_tools_sha256']
            if type(hashes) is not dict or not _ANALYSIS_TOOLS <= set(hashes) or len(hashes) > 8:
                return ''
            tools = {}
            for name, digest in hashes.items():
                if not re.fullmatch(r'[A-Za-z0-9_]+\.(py|json|md)', name):
                    return ''
                source = policy.Path_Resolve('Tools/' + name, allow_root=False)
                if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                    return ''
                tools[name] = {'path': str(source), 'sha256': digest}
            review = report['software_review']
            manifest = Manifest_Load(expected_root, Path(tools['software_stack_inputs.json']['path']),
                                     tools['software_stack_inputs.json']['sha256'])
            cases = [case for case in manifest['cases'] if case['name'] == review['case'] and
                     case['configuration'] == report['configuration']]
            if (len(cases) != 1 or manifest['review_revision'] != review['revision'] or
                    cases[0]['review_document'] != 'Tools/' + review['document'] or
                    cases[0]['review_document_sha256'] != review['document_sha256'] or
                    cases[0]['compiled_artifacts'].get(relative.name) != report['elf_sha256'] or
                    cases[0]['compiler'] != report['compiler'] or
                    tools[review['document']]['sha256'] != review['document_sha256']):
                return ''
            case_file = manifest['sealed_case_files'].get(review['case'])
            if case_file is not None and (report.get('software_review', {}).get('case_file') != case_file or
                                         'stack_manifest.py' not in tools):
                return ''
            value.update(analysis_tools=tools, software_review=review,
                         main_msp_exceptions={key: report['main_msp_exceptions'][key] for key in _MSP_FIELDS})
        value.update(target="flight", report_path=str(path),
                     report_sha256=hashlib.sha256(raw).hexdigest(), artifacts=artifacts)
        summary = _PREFIX + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return summary if ArtifactStackReportSummary_Decode(summary) else ""
    except (OSError, ValueError, KeyError, TypeError, IndexError, WorkspacePolicyError):
        return ""


def ArtifactStackReportSummary_Decode(summary: str) -> dict | None:
    if not summary.startswith(_PREFIX) or len(summary) > 131072:
        return None
    try:
        value = json.loads(summary[len(_PREFIX):])
        if value["target"] != "flight" or type(value["passes"]) is not bool:
            return None
        scope = value["whole_program_stack_acceptance"]
        software = scope in ('SOFTWARE BOUND PASS', 'SOFTWARE BOUND FAIL')
        if not software and not str(scope).startswith("NOT PROVEN:"):
            return None
        minimum = value["minimum_margin_bytes"]
        if type(minimum) is not int or minimum < 0:
            return None
        if type(value["checks"]) is not dict or not value["checks"] or not all(
                type(item) is bool for item in value["checks"].values()):
            return None
        if type(value["tasks"]) is not list or not 1 <= len(value["tasks"]) <= 32:
            return None
        names = set()
        for task in value["tasks"]:
            name = task["task"]
            if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name) or name in names:
                return None
            names.add(name)
            for key in ("configured_bytes", "call_chain_bytes", "context_bytes", "worst_known_bytes"):
                if type(task[key]) is not int or task[key] < 0:
                    return None
            if (task["configured_bytes"] <= 0 or type(task["margin_bytes"]) is not int or
                    task["worst_known_bytes"] != task["call_chain_bytes"] + task["context_bytes"] or
                    task["margin_bytes"] != task["configured_bytes"] - task["worst_known_bytes"] or
                    type(task["passes"]) is not bool or task["passes"] != (task["margin_bytes"] >= minimum)):
                return None
            chain = task["chain"]
            if type(chain) is not list or not 1 <= len(chain) <= 128 or any(
                    type(frame["function"]) is not str or len(frame["function"]) > 256 or
                    type(frame["frame_bytes"]) is not int or frame["frame_bytes"] < 0 for frame in chain):
                return None
            if sum(frame['frame_bytes'] for frame in chain) != task['call_chain_bytes']:
                return None
        expected = all(value["checks"].values()) and all(task["passes"] for task in value["tasks"])
        if software:
            if minimum < 256 or any(task['context_bytes'] < 256 for task in value['tasks']):
                return None
            msp = value['main_msp_exceptions']
            if (set(msp) != set(_MSP_FIELDS) or any(type(msp[key]) is not int or msp[key] < 0
                    for key in _MSP_FIELDS if key not in ('passes', 'margin_bytes')) or
                    type(msp['margin_bytes']) is not int or type(msp['passes']) is not bool or
                    msp['configured_bytes'] <= 0 or msp['priority_bits'] != 4 or
                    msp['priority_levels'] not in (4, 16) or msp['exception_frame_bytes'] != 108):
                return None
            worst = (msp['main_reset_bytes'] + msp['priority_levels'] *
                     (msp['maximum_configurable_handler_bytes'] + msp['exception_frame_bytes']) +
                     msp['fixed_handler_bytes'] + 2 * msp['exception_frame_bytes'])
            if (msp['worst_known_bytes'] != worst or msp['margin_bytes'] != msp['configured_bytes'] - worst or
                    msp['passes'] != (msp['margin_bytes'] >= minimum)):
                return None
            tools = value['analysis_tools']
            review = value['software_review']
            if (type(tools) is not dict or not _ANALYSIS_TOOLS <= set(tools) or len(tools) > 8 or
                    any(not re.fullmatch(r'[A-Za-z0-9_]+\.(py|json|md)', name) or
                        type(item['path']) is not str or
                        not re.fullmatch(r'[0-9a-f]{64}', item['sha256']) for name, item in tools.items()) or
                    any(type(review[key]) is not str or not 1 <= len(review[key]) <= 256
                        for key in ('case', 'revision', 'document', 'document_sha256')) or
                    tools[review['document']]['sha256'] != review['document_sha256']):
                return None
            case_file = review.get('case_file')
            if case_file is not None and (type(case_file) is not dict or
                    set(case_file) != {'path', 'sha256'} or
                    re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', review['case']) is None or
                    case_file['path'] != 'Tools/software_stack_cases/' + review['case'] + '.json' or
                    type(case_file['sha256']) is not str or
                    re.fullmatch(r'[0-9a-f]{64}', case_file['sha256']) is None or
                    'stack_manifest.py' not in tools):
                return None
            expected = expected and msp['passes']
            if (scope == 'SOFTWARE BOUND PASS') != expected:
                return None
        if value["passes"] != expected:
            return None
        if (type(value['artifacts']) is not dict or set(value['artifacts']) != {'elf', 'checker'} or
                type(value['report_path']) is not str):
            return None
        for digest in (value["report_sha256"], *(item["sha256"] for item in value["artifacts"].values())):
            if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                return None
        return value
    except (ValueError, KeyError, TypeError):
        return None
