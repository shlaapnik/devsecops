# devsecops

[English version](README.md)

В этом репозитории находится DevSecOps-пайплайн для GitHub Actions и GitLab CI. Пайплайн
проверяет секреты, код, зависимости, Dockerfile, образы контейнеров и CI-конфигурацию. Пайплайн
сам обновляет сканеры. Тест на canary проверяет каждое обновление сканера до того, как оно
попадёт в пайплайн.

## Быстрый старт

Пайплайн не копируется в проект. В проекте лежит короткий файл со ссылкой на релиз этого
репозитория. Когда выходит новый релиз, Renovate обновляет ссылку.

1. Клонируйте этот репозиторий:

   ```bash
   git clone --depth 1 https://github.com/shlaapnik/devsecops
   ```

2. Запустите скрипт для своего проекта:

   ```bash
   devsecops/scripts/bootstrap.sh путь/к/проекту
   ```

   Скрипт определяет платформу по remote `origin` проекта. Скрипт добавляет файл пайплайна,
   конфигурацию Renovate и файлы исключений. Существующие файлы скрипт не меняет.

3. Выполните шаги из строк `todo` и `next` в выводе скрипта.

Пример вывода для нового проекта в GitHub:

```text
platform github, pipeline version v0.1.0
add   .github/workflows/devsecops.yml
add   .betterleaksignore
...
add   renovate.json

next  commit the changes:
        cd путь/к/проекту
        git add .github/workflows/devsecops.yml .betterleaksignore ... renovate.json
        git commit -m "Add the DevSecOps pipeline"
next  install the Renovate app in the repository: https://github.com/apps/renovate
next  in the branch ruleset, make "Scan / Gate" a required check
```

ПРИМЕЧАНИЕ: Скрипту нужны bash и git. В Windows используйте Git Bash.

Чтобы установить пайплайн без скрипта, выполните шаги из разделов
[Установка в GitHub](#установка-в-github) или [Установка в GitLab](#установка-в-gitlab).

## Проверки

| Проверка | GitHub Actions | GitLab CI | Проверка не проходит, если |
| --- | --- | --- | --- |
| Секреты в истории git | Betterleaks | Betterleaks | Betterleaks находит секрет со средней или высокой уверенностью |
| CI-конфигурация | zizmor, actionlint | poutine | zizmor находит проблему уровня medium или high, или actionlint или poutine находят проблему |
| Код | Semgrep CE, `p/default` | Semgrep CE, `p/default` | правило уровня ERROR находит проблему |
| Зависимости | Grype | Grype | уязвимость уровня high или critical имеет исправленную версию |
| Dockerfile | hadolint | hadolint | hadolint находит ошибку |
| Образ контейнера | Docker, Grype | kaniko, Grype | уязвимость уровня high или critical имеет исправленную версию |

Уязвимость без исправленной версии не останавливает пайплайн. Обновление не может устранить
такую уязвимость.

Grype показывает значение EPSS для каждой уязвимости. EPSS — это вероятность того, что
злоумышленники используют уязвимость в ближайшие 30 дней.

Каждая job сохраняет отчёты в артефактах запуска. Отчёты — это файлы SARIF и SBOM в формате
CycloneDX. В публичных репозиториях GitHub пайплайн также отправляет SARIF в Code Scanning.
В GitLab job публикуют отчёты SAST, CycloneDX и Code Quality.

## Установка в GitHub

1. Добавьте в проект файл `.github/workflows/devsecops.yml`:

   ```yaml
   name: DevSecOps
   on:
     push:
       branches: [main]
     pull_request:
     schedule:
       - cron: "23 3 * * *"
   permissions: {}
   jobs:
     scan:
       name: Scan
       uses: shlaapnik/devsecops/.github/workflows/scan.yml@<commit-sha> # vX.Y.Z
       permissions:
         actions: read
         contents: read
         security-events: write
   ```

2. Замените `<commit-sha>` и `vX.Y.Z` на значения последнего релиза. Не удаляйте комментарий:
   по нему Renovate находит релиз.
3. Добавьте файл `renovate.json` с содержимым `{"extends": ["github>shlaapnik/devsecops"]}`.
4. Установите в репозиторий [приложение Renovate](https://github.com/apps/renovate).
5. В ruleset ветки сделайте `Scan / Gate` обязательной проверкой.

ПРИМЕЧАНИЕ: Ночной запуск находит новые уязвимости в коде, который не менялся.

ПРИМЕЧАНИЕ: Renovate мёржит pull request, только если все обязательные проверки прошли.

Шаги 1–3 выполняет скрипт из раздела [Быстрый старт](#быстрый-старт). Скрипт также добавляет
файлы исключений.

## Установка в GitLab

1. Добавьте в `.gitlab-ci.yml` этот `include`:

   ```yaml
   include:
     - remote: https://raw.githubusercontent.com/shlaapnik/devsecops/<commit-sha>/templates/devsecops.yml # vX.Y.Z
       inputs:
         enforce: true
   ```

2. Замените `<commit-sha>` и `vX.Y.Z` на значения последнего релиза. Не удаляйте комментарий:
   по нему Renovate находит релиз.
3. Убедитесь, что в проекте есть стадия `test`. Если её нет, задайте input `stage`.
4. Убедитесь, что раннеры используют Docker executor или Kubernetes executor.
5. Убедитесь, что раннеры используют стандартный `umask 0000`.
6. Настройте Renovate в отдельном проекте. Это делается один раз для всех проектов группы.
   Используйте файл [onboarding/gitlab-renovate-bot/.gitlab-ci.yml](onboarding/gitlab-renovate-bot/.gitlab-ci.yml).
7. Добавьте в проект ночное расписание пайплайна.

Шаг 1 выполняет скрипт из раздела [Быстрый старт](#быстрый-старт). Скрипт также добавляет файлы
исключений.

ПРИМЕЧАНИЕ: Job не используют privileged-режим. kaniko собирает образ без Docker-демона.

ПРИМЕЧАНИЕ: По умолчанию job запускаются только в пайплайнах веток. Поэтому include не добавляет
в проект пайплайн merge request. Если в проекте уже есть пайплайны merge request, задайте
`merge-request-pipelines: true`. Тогда job запускаются в пайплайне merge request и не повторяются
в пайплайне ветки.

Job используют такие коды выхода:

| Код | Значение | Статус job |
| --- | --- | --- |
| 0 | Сканер не нашёл проблем. | passed |
| 1 | Сканер нашёл проблемы, `enforce` равен `true`. | failed |
| 2 | Сканер нашёл проблемы и `enforce` равен `false`, или изменился файл исключений. | passed с предупреждением |
| 3 | Сканер не сработал. | failed |

Репозиторий можно зеркалировать в ваш GitLab. Тогда используйте файл как CI/CD-компонент:
`component: $CI_SERVER_FQDN/<группа>/devsecops/devsecops@<версия>`.

## Обновления

### Обновления сканеров

1. Renovate находит новую версию сканера.
2. Renovate ждёт 7 дней после даты релиза.
3. Renovate открывает pull request в этом репозитории.
4. Self-test запускает пайплайны GitHub и GitLab на [canary/](canary/).
5. Если сканер не находит хотя бы одну находку из [canary/expected.yml](canary/expected.yml), self-test не проходит.
6. Если self-test прошёл, Renovate мёржит minor- или patch-обновление.

ПРИМЕЧАНИЕ: Каждое major-обновление проверяет человек.

ПРИМЕЧАНИЕ: Дату релиза образа даёт только Docker Hub. Для образов из других реестров, например
ghcr.io, Renovate не может ждать 7 дней. Renovate сразу открывает pull request, а человек мёржит
его через 7 дней после релиза.

ПРИМЕЧАНИЕ: В марте 2026 года злоумышленники выпустили вредоносный релиз Trivy. Команда Trivy
удалила его меньше чем за сутки. Задержка в 7 дней защищает от таких атак.

### Обновления зависимостей в проекте

Общий пресет Renovate [default.json](default.json) делает следующее:

- Закрепляет actions, образы и зависимости по digest.
- Ждёт 7 дней перед обычным обновлением.
- Сразу предлагает исправление уязвимости.
- Мёржит patch-обновления, обновления digest, pin и lock-файлов, если все проверки прошли.
- Мёржит minor-обновления пакетов версии 1.0 и выше, если все проверки прошли.
- Каждую неделю обновляет lock-файлы. Так в проект попадают исправления транзитивных зависимостей.
- Не мёржит обновления образов из реестров, кроме Docker Hub. Эти реестры не дают дату релиза,
  поэтому Renovate не может ждать 7 дней. Такие обновления мёржит человек.

Renovate не может задержать транзитивные обновления и еженедельное обновление lock-файлов. Задайте
ту же задержку в менеджере пакетов:

- uv: добавьте `exclude-newer = "7 days"` в таблицу `[tool.uv]` файла `pyproject.toml`.
- pnpm: добавьте `minimumReleaseAge: 10080` в `pnpm-workspace.yaml`.
- npm 11.10 и новее: добавьте `min-release-age=7` в `.npmrc`.
- Yarn 4.10 и новее: добавьте `npmMinimalAgeGate: 10080` в `.yarnrc.yml`.

Скрипт `bootstrap.sh` показывает отсутствующую настройку строкой `todo`.

### Обновления пайплайна в проекте

Проект использует SHA коммита релиза. Тег можно перенести на другой коммит, SHA — нельзя.
Комментарий после SHA показывает релиз. Renovate обновляет SHA и комментарий в отдельном pull request:

- в GitHub — в строке `uses` в workflow;
- в GitLab — в URL `include: remote`. Правило для этого URL есть в общем пресете.

Вместо SHA можно указать `main`. Тогда проект получает каждое изменение без pull request. Renovate
не меняет `main`. В GitHub zizmor разрешает `main` благодаря строке
`"shlaapnik/devsecops/*": ref-pin` в `.github/zizmor.yml`.

## Несовместимые обновления

Renovate не знает, совместима ли новая версия. Renovate опирается на номер версии и на проверки CI.

- Renovate не мёржит major-обновления. Миграцию выполняет человек или ИИ-агент.
- Renovate не мёржит minor-обновления пакетов `0.x`. Такие обновления могут изменить API.
- Renovate мёржит patch-обновления, только если все обязательные проверки прошли.

ВНИМАНИЕ: Автоматический мёрж безопасен настолько, насколько хороши ваши тесты. Если в проекте
нет тестов, дефектное patch-обновление пройдёт проверки. Добавьте тесты или отключите
автоматический мёрж в этом проекте.

Новая версия сканера может найти больше проблем. Это не ошибка совместимости, но проверки могут
не пройти.

- Если проект закреплён на релизе, новые проблемы видны в pull request от Renovate. Вы увидите
  их до мёржа.
- Если проект использует `@main`, новые проблемы появятся в следующем запуске.

## Inputs

| Input | По умолчанию | Назначение |
| --- | --- | --- |
| `enforce` | `true` | `false` показывает проблемы без отказа. GitLab показывает предупреждение. |
| `skip` | пусто | Проверки, которые надо пропустить, через запятую: `secrets`, `ci`, `sast`, `deps`, `dockerfiles`, `image`. |
| `fail-on-severity` | `high` | Минимальный уровень исправимой уязвимости, который останавливает пайплайн. |
| `secrets-confidence` | `medium` | Минимальная уверенность Betterleaks, которую показывает отчёт. |
| `semgrep-config` | `p/default` | Наборы правил Semgrep через пробел. Папку `.semgrep/` пайплайн добавляет сам. |
| `semgrep-args` | пусто | Дополнительные аргументы Semgrep. |
| `dockerfile` | `Dockerfile` | Dockerfile для проверки образа. |
| `docker-context` | `.` | Контекст сборки для проверки образа. |
| `path` | `.` | Папка, которую надо проверить в монорепозитории. |
| `upload-sarif` | `true` | Только GitHub. Отправляет SARIF в Code Scanning. Приватные репозитории пайплайн пропускает. |
| `report-name` | `devsecops` | Только GitHub. Префикс артефактов, если один запуск вызывает workflow два раза. |
| `stage` | `test` | Только GitLab. Стадия job. |
| `merge-request-pipelines` | `false` | Только GitLab. `true`, если в проекте есть пайплайны merge request. |

## Подключение к существующему проекту

1. Для первых запусков задайте `enforce: false`.
2. Прочитайте сводку запуска.
3. Исправьте проблемы, которые можете исправить.
4. Остальные проблемы оформите как исключения. Используйте таблицу ниже.
5. Задайте `enforce: true`.

Скрипт `scripts/bootstrap.sh` добавляет файлы исключений. В каждом файле есть пример. Если вы не
используете скрипт, скопируйте файлы из [onboarding/](onboarding/).

Скрипт не меняет и не заменяет существующие файлы:

- Инструмент может читать конфигурацию под разными именами. Если файл есть под одним из этих
  имён, скрипт не добавляет файл. Новый файл мог бы скрыть существующий.
- Если существующий файл должен содержать настройку пайплайна, скрипт показывает строку `todo`.
  Строка говорит, какую настройку добавить и куда. Добавьте настройку вручную.
- Для каждого существующего файла скрипт показывает строку `keep`.

| Файл, который добавляет скрипт | Другие имена, которые проверяет скрипт |
| --- | --- |
| `.github/workflows/devsecops.yml` | Любой workflow, который вызывает `scan.yml`. |
| `renovate.json` | `renovate.json5`, `.github/renovate.json`, `.github/renovate.json5`, `.gitlab/renovate.json`, `.gitlab/renovate.json5`, `.renovaterc`, `.renovaterc.json`, `.renovaterc.json5`, секция `renovate` в `package.json`. |
| `.betterleaksignore` | `.gitleaksignore` |
| `.grype.yaml` | `.grype.yml`, `.grype/config.yaml`, `.grype/config.yml` |
| `.hadolint.yaml` | `.hadolint.yml` |
| `.github/zizmor.yml` | `zizmor.yml` |
| `.github/actionlint.yaml` | `.github/actionlint.yml` |
| `.poutine.yml` | `.github/poutine.yml` |

| Проблема | Файл исключений |
| --- | --- |
| Ложный секрет или секрет, который вы уже заменили | Добавьте fingerprint в `.betterleaksignore`. |
| Много старых секретов в истории git | Создайте baseline. Используйте команду ниже. |
| Уязвимость, которую сейчас нельзя исправить | Добавьте её в `.grype.yaml`. Укажите причину и дату пересмотра. |
| Тестовые данные с уязвимыми зависимостями | Добавьте путь в `exclude` в `.grype.yaml`, например `./tests/data/**`. |
| Ложная проблема SAST | Добавьте путь в `.semgrepignore` или задайте `semgrep-args: --exclude-rule <id>`. |
| Правило для CI-конфигурации | Используйте `.github/zizmor.yml`, `.github/actionlint.yaml` или `.poutine.yml`. |
| Правило hadolint | Добавьте его в `.hadolint.yaml`, например `ignored: [DL3008]`. |

Чтобы создать baseline секретов, сначала замените секреты. Затем выполните команду:

```bash
docker run --rm -v "$PWD:/src" -w /src ghcr.io/betterleaks/betterleaks:v1.10.0 \
  git --redact --confidence medium --exit-code 0 \
  --report-format json --report-path .devsecops/betterleaks-baseline.json .
```

Пример `.grype.yaml`:

```yaml
ignore:
  - vulnerability: GHSA-xxxx-xxxx-xxxx
    reason: Проект не вызывает уязвимый код. Пересмотреть до 2026-12-15.
```

## ИИ-агенты

Исключения находятся только в файлах, которые видны в ревью. ИИ-агент может добавить в код
комментарий-исключение, чтобы проверка прошла. Поэтому пайплайн игнорирует такие комментарии:
`nosemgrep`, `gitleaks:allow`, `betterleaks:allow` и `# hadolint ignore=`.

Пайплайн показывает предупреждение, если pull request:

- меняет файл исключений;
- меняет настройку пайплайна, например `enforce` или `skip`. В GitHub пайплайн проверяет workflow,
  который вызывает `scan.yml`. В GitLab — `.gitlab-ci.yml`;
- добавляет или удаляет комментарий `# zizmor: ignore` в workflow или action GitHub. zizmor
  выполняет такие комментарии.

- Если обновление от Renovate сломало сборку, поручите агенту миграцию в том же pull request.
  Для Claude Code один раз выполните `/install-github-app`. Затем напишите `@claude` в pull request.
- Сводка и аннотации показывают файл и строку каждой проблемы. Агент использует эти данные,
  чтобы исправить проблему.
- Если у вас есть GitHub Code Security, назначайте Dependabot alerts на Copilot, Claude или Codex.

## Ограничения

- Semgrep скачивает `p/default` из реестра при каждом запуске. Новые правила могут появиться
  без изменений в этом репозитории.
- GitHub отключает запуски по расписанию, если в репозитории 60 дней нет активности.
- Проверка образа собирает образ без build args и секретов.
- kaniko нужны учётные данные реестра для приватного базового образа.
- GitLab.com ограничивает размер артефакта 1 ГБ. Большой образ может превысить этот предел.
- Если проверка образа не работает в вашем проекте, задайте `skip: image`. Затем сканируйте
  опубликованный образ в пайплайне деплоя.
- Dependabot может показывать алерты для зависимостей в `canary/` этого репозитория. Так и должно
  быть: canary содержит эти уязвимости специально.

## Что не входит

- DAST, например ZAP или Nuclei. Для DAST нужен запущенный стенд. Добавьте DAST в пайплайн деплоя.
- Файлы Terraform и Kubernetes. Используйте Checkov или `trivy config`.
- Подпись образов и admission control. Используйте cosign и Kyverno в пайплайне деплоя.
- ML-модели в формате pickle. Используйте ModelScan или ModelAudit. Формат safetensors безопаснее.

## Файлы репозитория

```text
.github/workflows/scan.yml       Переиспользуемый workflow для GitHub.
.github/workflows/self-test.yml  Сканирование и линт этого репозитория, запуски на canary.
templates/devsecops.yml          CI/CD-компонент для GitLab.
default.json                     Общий пресет Renovate для проектов.
renovate.json                    Конфигурация Renovate этого репозитория.
canary/                          Проект с известными проблемами для self-test.
onboarding/                      Файлы, которые bootstrap.sh копирует в проект.
onboarding/gitlab-renovate-bot/  Отдельный проект Renovate для GitLab. Скрипт его не копирует.
scripts/                         Скрипт bootstrap, раннер GitLab-компонента и проверка canary.
```

## Лицензия

[MIT](LICENSE)
