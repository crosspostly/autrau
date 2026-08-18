# `.planning/` — GSD Project Planning

> Это структура для планирования проекта **autrau** по методологии GSD (Get Stuff Done). Используется AI-агентами и человеком для понимания текущего состояния, требований и roadmap.

## Файлы

| Файл | Назначение |
|------|------------|
| `PROJECT.md` | Описание проекта: что это, tech stack, repository layout, key decisions |
| `MILESTONES.md` | История версий (что было сделано в v1.0, v1.1, ..., v1.5) |
| `REQUIREMENTS.md` | Детальные требования с REQ-IDs и acceptance criteria |
| `ROADMAP.md` | Поэтапный план текущего milestone с sub-phases, tasks, tests |
| `STATE.md` | Current position, blockers, todos, recent commits, open questions |
| `AGENTS.md` | **Главная точка входа для AI-агентов** — conventions, pitfalls, workflow |

## Текущий milestone: v1.5 — Handi-like UX

**Цель:** превратить autrau в «Handi-стайл» desktop-transcription:
- 🔄 Горячие клавиши для реал-тайм записи (как Handi)
- 🔄 Автоперевод ru→en после расшифровки
- 🔄 Вкладка «Голосовые заметки» в расшифровках
- ✅ Расширение файла в имени транскрипта (Phase 1)
- ✅ Размер в КБ для маленьких файлов (Phase 1)

См. [ROADMAP.md](ROADMAP.md) для детального плана.

## Как пользоваться

### Если ты AI-агент

1. **Начни с `AGENTS.md`** — там conventions, pitfalls, workflow
2. Прочитай `STATE.md` чтобы понять, где сейчас проект
3. Прочитай `REQUIREMENTS.md` чтобы понять, что нужно сделать
4. Прочитай `ROADMAP.md` чтобы понять, в каком порядке
5. Делай задачи, обновляй STATE.md по мере прогресса

### Если ты человек

1. `PROJECT.md` — общая картина
2. `MILESTONES.md` — что было сделано
3. `ROADMAP.md` — что делается сейчас
4. `STATE.md` — где мы прямо сейчас + open questions

## Обновление

После каждой phase transition:
- `STATE.md` — отметить todos done
- `ROADMAP.md` — обновить статус phase
- `MILESTONES.md` — НЕ обновлять до конца milestone (через `/gsd-complete-milestone`)

После завершения milestone:
- `MILESTONES.md` — добавить v1.5 в shipped
- `PROJECT.md` — обновить секцию "Current Milestone"
- `STATE.md` — reset для нового milestone

## GSD Skills

- `/gsd-new-milestone` — начать новый milestone
- `/gsd-discuss-phase` — обсудить phase перед планированием
- `/gsd-plan-phase` — детально спланировать phase
- `/gsd-execute-phase` — выполнить phase с wave-based parallelization
- `/gsd-verify-work` — verify через UAT
- `/gsd-complete-milestone` — закрыть milestone

---

*Created: 2026-08-19. Maintained by AI-агенты + human.*
