#!/usr/bin/env bash
# PD CLI bash completion script
# Source this file or copy to /etc/bash_completion.d/pd
# Usage: source pd-completion.bash

_pd() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="init status validate checkpoint verify advance complete-task config list delete history report diff completion"

    # Global flags
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "--feature --json --dry-run --force --no-color -f -h --help" -- "$cur") )
        return 0
    fi

    # Subcommand completion
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    local subcmd="${COMP_WORDS[1]}"
    case "$subcmd" in
        init)
            ;;
        complete-task)
            ;;
        checkpoint)
            COMPREPLY=( $(compgen -W "--note -n" -- "$cur") )
            ;;
        validate)
            COMPREPLY=( $(compgen -W "--deep" -- "$cur") )
            ;;
        delete)
            COMPREPLY=( $(compgen -W "--archive --force" -- "$cur") )
            ;;
        list|status|verify|advance|config|history|report|diff)
            COMPREPLY=( $(compgen -W "--feature -f --json" -- "$cur") )
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
            ;;
    esac
}
complete -F _pd pd
