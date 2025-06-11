---
created: 2025-06-11T03:11:23 (UTC +01:00)
tags: []
source: https://copier.readthedocs.io/en/stable/creating/#loop-over-lists-to-generate-files-and-directories
author: 
---

# Creating a template - copier

> ## Excerpt
> Library and command-line utility for rendering projects templates.

---
A template is a directory: usually the root folder of a Git repository.

The content of the files inside the project template is copied to the destination without changes, **unless they end with `.jinja`** (or [your chosen suffix](https://copier.readthedocs.io/en/stable/configuring/#templates_suffix "templates_suffix")). In that case, the templating engine will be used to render them.

Jinja2 templating is used. Learn more about it by reading [Jinja2 documentation](https://jinja.palletsprojects.com/).

If a **YAML** file named `copier.yml` or `copier.yaml` is found in the root of the project, the user will be prompted to fill in or confirm the default values.

## Minimal example[¶](https://copier.readthedocs.io/en/stable/creating/#minimal-example "Permanent link")

```
📁 my_copier_template                            # your template project
├── 📄 copier.yml                                # your template configuration
├── 📁 .git/                                     # your template is a Git repository
├── 📁 {{project_name}}                          # a folder with a templated name
│   └── 📄 {{module_name}}.py.jinja              # a file with a templated name
└── 📄 {{_copier_conf.answers_file}}.jinja       # answers are recorded here

```

copier.yml

```
# questions
project_name:
    type: str
    help: What is your project name?

module_name:
    type: str
    help: What is your Python module name?

```

{{project\_name}}/{{module\_name}}.py.jinja

```
print("Hello from {{module_name}}!")

```

{{\_copier\_conf.answers\_file}}.jinja

```
# Changes here will be overwritten by Copier
{{ _copier_answers|to_nice_yaml -}}

```

Generating a project from this template with `super_project` and `world` as answers for the `project_name` and `module_name` questions respectively would create in the following directory and files:

```
📁 generated_project
├── 📁 super_project
│   └── 📄 world.py
└── 📄 .copier-answers.yml

```

super\_project/world.py

```
print("Hello from world!")

```

.copier-answers.yml

```
# Changes here will be overwritten by Copier
_commit: 0.1.0
_src_path: gh:your_account/your_template
project_name: super_project
module_name: world

```

Copier allows much more advanced templating: see the next chapter, [configuring a template](https://copier.readthedocs.io/en/stable/configuring/), to see all the configurations options and their usage.

## Template helpers[¶](https://copier.readthedocs.io/en/stable/creating/#template-helpers "Permanent link")

In addition to [all the features Jinja supports](https://jinja.palletsprojects.com/en/3.1.x/templates/), Copier provides all functions and filters from [jinja2-ansible-filters](https://gitlab.com/dreamer-labs/libraries/jinja2-ansible-filters/). This includes the `to_nice_yaml` filter, which is used extensively in our context.

## Variables (global)[¶](https://copier.readthedocs.io/en/stable/creating/#variables-global "Permanent link")

The following variables are always available in Jinja templates:

### `_copier_answers`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_answers "Permanent link")

`_copier_answers` includes the current answers dict, but slightly modified to make it suitable to [autoupdate your project safely](https://copier.readthedocs.io/en/stable/configuring/#the-copier-answersyml-file "The .copier-answers.yml file"):

-   It doesn't contain secret answers.
-   It doesn't contain any data that is not easy to render to JSON or YAML.
-   It contains special keys like `_commit` and `_src_path`, indicating how the last template update was done.

### `_copier_conf`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_conf "Permanent link")

`_copier_conf` includes a representation of the current Copier [Worker](https://copier.readthedocs.io/en/stable/reference/main/#copier._main.Worker) object, also slightly modified:

-   It only contains JSON-serializable data.
-   You can serialize it with `{{ _copier_conf|to_json }}`.
-   ⚠️ It contains secret answers inside its `.data` key.
-   Modifying it doesn't alter the current rendering configuration.

Furthermore, the following keys are added:

#### `os`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_conf.os "Permanent link")

The detected operating system, either `"linux"`, `"macos"`, `"windows"` or `None`.

#### `sep`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_conf.sep "Permanent link")

The operating system-specific directory separator.

#### `vcs_ref_hash`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_conf.vcs_ref_hash "Permanent link")

The current commit hash from the template.

### `_copier_python`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_python "Permanent link")

The absolute path of the Python interpreter running Copier.

### `_external_data`[¶](https://copier.readthedocs.io/en/stable/creating/#_external_data "Permanent link")

A dict of the data contained in [external\_data](https://copier.readthedocs.io/en/stable/configuring/#external_data).

When rendering the template, that data will be exposed in the special `_external_data` variable:

-   Keys will be the same as in [external\_data](https://copier.readthedocs.io/en/stable/configuring/#external_data).
-   Values will be the files contents parsed as YAML. JSON is also compatible.
-   Parsing is done lazily on first use.

### `_folder_name`[¶](https://copier.readthedocs.io/en/stable/creating/#_folder_name "Permanent link")

The name of the project root directory.

### `_copier_phase`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_phase "Permanent link")

The current phase, one of `"prompt"`,`"tasks"`, `"migrate"` or `"render"`.

Note

There is also an additional `"undefined"` phase used when not in any phase. You may encounter this phase when rendering outside of those phases, when rendering lazily (and the phase notion can be irrelevant) or when testing.

## Variables (context-dependent)[¶](https://copier.readthedocs.io/en/stable/creating/#variables-context-dependent "Permanent link")

Some variables are only available in select contexts:

### `_copier_operation`[¶](https://copier.readthedocs.io/en/stable/creating/#_copier_operation "Permanent link")

The current operation, either `"copy"` or `"update"`.

Availability: [`exclude`](https://copier.readthedocs.io/en/stable/configuring/#exclude), [`tasks`](https://copier.readthedocs.io/en/stable/configuring/#tasks)

## Variables (context-specific)[¶](https://copier.readthedocs.io/en/stable/creating/#variables-context-specific "Permanent link")

Some rendering contexts provide variables unique to them:

-   [`migrations`](https://copier.readthedocs.io/en/stable/configuring/#migrations)

## Loop over lists to generate files and directories[¶](https://copier.readthedocs.io/en/stable/creating/#loop-over-lists-to-generate-files-and-directories "Permanent link")

You can use the special `yield` tag in file and directory names to generate multiple files or directories based on a list of items.

In the path name, `{% yield item from list_of_items %}{{ item }}{% endyield %}` will loop over the `list_of_items` and replace `{{ item }}` with each item in the list.

A looped `{{ item }}` will be available in the scope of generated files and directories.

copier.yml

```
commands:
    type: yaml
    multiselect: true
    choices:
        init:
            value: &init
                name: init
                subcommands:
                    - config
                    - database
        run:
            value: &run
                name: run
                subcommands:
                    - server
                    - worker
        deploy:
            value: &deploy
                name: deploy
                subcommands:
                    - staging
                    - production
    default: [*init, *run, *deploy]

```

```
📁 commands
└── 📁 {% yield cmd from commands %}{{ cmd.name }}{% endyield %}
    ├── 📄 __init__.py
    └── 📄 {% yield subcmd from cmd.subcommands %}{{ subcmd }}{% endyield %}.py.jinja

```

{% yield subcmd from cmd.subcommands %}{{ subcmd }}{% endyield %}.py.jinja

```
print("This is the `{{ subcmd }}` subcommand in the `{{ cmd.name }}` command")

```

If you answer with the default to the question, Copier will generate the following structure:

```
📁 commands
├── 📁 deploy
│   ├── 📄 __init__.py
│   ├── 📄 production.py
│   └── 📄 staging.py
├── 📁 init
│   ├── 📄 __init__.py
│   ├── 📄 config.py
│   └── 📄 database.py
└── 📁 run
    ├── 📄 __init__.py
    ├── 📄 server.py
    └── 📄 worker.py

```

Where looped variables `cmd` and `subcmd` are rendered in generated files:

commands/init/config.py

```
print("This is the `config` subcommand in the `init` command")

```
