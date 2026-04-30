# PJT_A 폴더 정리 Inventory

- 작성일: 2026-04-30
- 대상 프로젝트: `Project/PJT_A`
- 작업 유형: `plan-required operation`
- 정리 정책: 삭제보다 `98_archive/20260430_folder_cleanup/` 이동과 기록 보존 우선
- 코드 스코프: `Project/PJT_A/ps-docparser`
- 보고서/운영 기록 스코프: `Project/PJT_A/05_검증_리뷰`, `Project/PJT_A/폴더정리_및_Git_셋업_기록_20260420.md`

## 1. 사전 상태

Harness preflight 결과:

```text
task-type: plan-required operation
project: Project/PJT_A
summary: 2 WARN, 22 checks
WARN:
- Windows sandbox Google Drive ACL refresh failure
- Project git status is dirty: 110 entries
```

Git 상태 기준:

- 기존 tracked 삭제: `01_OCR_결과물/53-83 OKOK.pdf`
- 기존 modified 코드/테스트 다수: `ps-docparser/` 하위 기능 변경
- 기존 untracked 운영 문서와 신규 코드/테스트 다수: `04_Phase별_결과보고서`, `05_검증_리뷰`, `ps-docparser/`
- 이번 정리의 tracked 변경: `.gitignore`, `README.md`, 이 inventory, 문서 색인, 폴더/Git 기록
- 아카이브 이동 대상: Git ignored output/log 파일과 폴더

## 2. 유지한 항목

다음 항목은 증거, 원본, 운영 상태, 기능 변경 보호를 위해 이동하지 않았다.

- 실제 사용 코드와 테스트: `ps-docparser/` tracked/untracked 기능 파일
- 원본 자료: `00_견적서_원본/`
- 기존 OCR 결과 tracked 삭제 이슈: `01_OCR_결과물/53-83 OKOK.pdf`
- 운영/검증 문서: `04_Phase별_결과보고서/`, `05_검증_리뷰/*.md`, `05_검증_리뷰/*.log`
- 변경묶음 잠금: `05_검증_리뷰/PJT_A_변경묶음잠금_Manifest_20260428.md`, `.json`
- 환경/사용량 상태: `ps-docparser/.env`, `ps-docparser/output/ui_usage/usage.db`
- 기존 cold archive: `99_legacy_OCR/`

유지한 대표 `output/ui_runs`:

```text
phase15_lock_verification_logs
phase15_step12_ai_fallback_never_smoke2
ui_20260427_132845_f0649eb0
ui_20260427_141100_d12dec32
ui_20260427_141100_d12dec32_reprocess_check_v3
ui_20260427_143437_4d81e725
ui_20260427_143605_527b60b8
ui_20260427_153029_8a6502d4
ui_20260427_153029_8a6502d4_pdf_smoke_step8_lock
ui_20260427_153029_8a6502d4_reprocess_bugfix_check4
ui_20260427_policy_check_mixed2
ui_20260428_075409_121bef39
ui_20260428_085154_a929f3d1
ui_20260428_085154_a929f3d1_auto_localfirst_smoke
ui_20260428_094958_abc1c20f
ui_20260428_144919_e0be4ac4
ui_20260428_153630_620208a2
ui_20260428_batch_combined_excel_never_smoke
ui_20260428_batch_combined_excel_smoke
ui_20260428_data_quality_fix_smoke
ui_20260429_071951_5f8e4ade
ui_20260429_093812_3416d393
ui_20260429_103336_8ce3cd32
ui_20260429_low_cost_smoke
```

## 3. 아카이브 이동 항목

아카이브 위치:

```text
Project/PJT_A/98_archive/20260430_folder_cleanup/
```

`output_runs/`로 이동:

```text
phase15_step12_ai_fallback_never_smoke
ui_20260427_103828_37cac4b7
ui_20260427_111907_14bf505b
ui_20260427_112334_54e69916
ui_20260427_115515_8e784288
ui_20260427_130352_fc05d79c
ui_20260427_policy_check_mixed
ui_20260427_141100_d12dec32_reprocess_check
ui_20260427_141100_d12dec32_reprocess_check_v2
ui_20260427_144619_cbd1a175
ui_20260427_144619_cbd1a175_retry_fix
ui_20260427_150913_7a485259
ui_20260427_150913_7a485259_retry_dedupe
ui_20260427_150913_7a485259_retry_dedupe2
ui_20260427_153029_8a6502d4_reprocess_bugfix_check
ui_20260427_153029_8a6502d4_reprocess_bugfix_check2
ui_20260427_153029_8a6502d4_reprocess_bugfix_check3
ui_20260427_164847_36d8ed77
ui_20260428_153331_86228cf8
ui_20260429_103158_c7a4b45c
ui_20260429_163243_47981bbd
ui_20260429_163428_e60f2409
ui_20260429_163637_237ee48f
ui_20260429_164202_5d8215c9
ui_20260429_164446_d38202ee
```

`runtime_logs/`로 이동:

```text
dev_server_logs
ps-docparser.log
ui_20260428_batch_combined_excel_server_logs
ui_20260429_server_logs
```

`drive_conflicts/`:

```text
이번 실행에서는 별도 이동 없음
```

## 4. 삭제하지 않은 항목

- 실제 삭제 없음
- 빈 폴더 제거 없음
- `99_legacy_OCR/node_modules/`는 2차 정리 후보로만 기록

## 5. 검증

실행한 검증:

```text
python codex-harness/scripts/harness_guard.py preflight --project Project/PJT_A --task-type "plan-required operation"
python codex-harness/scripts/harness_guard.py doc-check --include-projects --strict
git -C Project/PJT_A status --short
git -C Project/PJT_A status --ignored --short
git -C Project/PJT_A diff --check
```

검증 결과:

- preflight: 2 WARN, 22 checks
- doc-check strict: 0 WARN, 17 checks
- git diff --check: pass
- `98_archive/`와 `ps-docparser/output/` ignored 상태 확인
- read-only sub-agent Explorer/Reviewer 검토 완료

## 6. 남은 위험

- 일부 기존 보고서는 아카이브된 run 이름을 명령 예시나 과거 증거로 언급할 수 있다.
- `98_archive/`는 Git ignored이므로 커밋 대상이 아니다.
- 기능 코드 dirty worktree가 크므로, 커밋 전에는 변경묶음 manifest 기준으로 별도 staging이 필요하다.
