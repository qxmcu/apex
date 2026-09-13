"""
Shell completion script generator for Apex CLI (Bash, Zsh, Fish).
"""

BASH_COMPLETION = """# Apex CLI Bash completion
_apex_completions() {
    local cur prev words cword
    _init_completion || return

    local commands="compress c decompress x extract test t list l repair fix heal benchmark b info i diff d completions"
    local modes="fast balanced ultra brute"
    local shells="bash zsh fish"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands -h --help -V --version" -- "$cur") )
        return 0
    fi

    local cmd="${words[1]}"
    case "$cmd" in
        compress|c)
            case "$prev" in
                -m|--mode)
                    COMPREPLY=( $(compgen -W "$modes" -- "$cur") )
                    return 0
                    ;;
                -o|--output|-b|--block-size|-p|--password)
                    _filedir
                    return 0
                    ;;
            esac
            COMPREPLY=( $(compgen -W "-o --output -m --mode -b --block-size -p --password -r --recovery --cdc -v --verbose -q --quiet -h --help" -- "$cur") )
            _filedir
            ;;
        decompress|x|extract)
            case "$prev" in
                -d|--dest)
                    _filedir -d
                    return 0
                    ;;
                -p|--password|-i|--include)
                    return 0
                    ;;
            esac
            COMPREPLY=( $(compgen -W "-d --dest -p --password -i --include -q --quiet -h --help" -- "$cur") )
            _filedir apx
            ;;
        diff|d)
            COMPREPLY=( $(compgen -W "-p --password --json -h --help" -- "$cur") )
            _filedir apx
            ;;
        test|t|list|l)
            COMPREPLY=( $(compgen -W "-p --password -h --help" -- "$cur") )
            _filedir apx
            ;;
        repair|fix|heal)
            case "$prev" in
                -o|--output)
                    _filedir apx
                    return 0
                    ;;
            esac
            COMPREPLY=( $(compgen -W "-o --output -p --password -h --help" -- "$cur") )
            _filedir apx
            ;;
        benchmark|b)
            COMPREPLY=( $(compgen -W "--max-sample-mb -h --help" -- "$cur") )
            _filedir
            ;;
        info|i)
            COMPREPLY=( $(compgen -W "-h --help" -- "$cur") )
            _filedir
            ;;
        completions)
            COMPREPLY=( $(compgen -W "$shells" -- "$cur") )
            ;;
    esac
}
complete -F _apex_completions apex
"""

ZSH_COMPLETION = """#compdef apex

_apex() {
    local curcontext="$curcontext" state line
    typeset -A opt_args

    local -a subcommands
    subcommands=(
        'compress:Compress a file or folder into an .apx archive'
        'c:Alias for compress'
        'decompress:Decompress an .apx archive'
        'x:Alias for decompress'
        'extract:Alias for decompress'
        'diff:Compare two .apx archives'
        'd:Alias for diff'
        'test:Test archive integrity without writing to disk'
        't:Alias for test'
        'list:List contents of an .apx archive'
        'l:Alias for list'
        'repair:Self-heal damaged .apx archive using recovery parity'
        'fix:Alias for repair'
        'heal:Alias for repair'
        'benchmark:Benchmark shootout against standard archivers'
        'b:Alias for benchmark'
        'info:Analyze Shannon entropy and compressibility'
        'i:Alias for info'
        'completions:Generate shell completion script'
    )

    _arguments -C \\
        '(-V --version)'{-V,--version}'[Show version]' \\
        '(-h --help)'{-h,--help}'[Show help]' \\
        '1: :->subcmd' \\
        '*:: :->args'

    case $state in
        subcmd)
            _describe -t commands 'apex subcommands' subcommands
            ;;
        args)
            case $line[1] in
                compress|c)
                    _arguments \\
                        '(-o --output)'{-o,--output}'[Output .apx file path]:file:_files' \\
                        '(-m --mode)'{-m,--mode}'[Preset mode]:mode:(fast balanced ultra brute)' \\
                        '(-b --block-size)'{-b,--block-size}'[Block size in MB]:size:' \\
                        '(-p --password)'{-p,--password}'[Password for encryption]:password:' \\
                        '(-r --recovery)'{-r,--recovery}'[Embed Reed-Solomon parity records]' \\
                        '--cdc[Enable Content-Defined Chunking]' \\
                        '(-v --verbose)'{-v,--verbose}'[Verbose output]' \\
                        '(-q --quiet)'{-q,--quiet}'[Quiet mode]' \\
                        '*:target:_files'
                    ;;
                decompress|x|extract)
                    _arguments \\
                        '(-d --dest)'{-d,--dest}'[Destination folder]:dir:_files -/' \\
                        '(-p --password)'{-p,--password}'[Archive password]:password:' \\
                        '*-i[Include pattern for selective extraction]:pattern:' \\
                        '*--include[Include pattern for selective extraction]:pattern:' \\
                        '(-q --quiet)'{-q,--quiet}'[Quiet mode]' \\
                        '1:archive:_files -g "*.apx"' \\
                        '*:files to extract:_files'
                    ;;
                diff|d)
                    _arguments \\
                        '(-p --password)'{-p,--password}'[Password]:password:' \\
                        '--json[Output diff as JSON]' \\
                        '1:first archive:_files -g "*.apx"' \\
                        '2:second archive:_files -g "*.apx"'
                    ;;
                test|t|list|l)
                    _arguments \\
                        '(-p --password)'{-p,--password}'[Password]:password:' \\
                        '1:archive:_files -g "*.apx"'
                    ;;
                repair|fix|heal)
                    _arguments \\
                        '(-o --output)'{-o,--output}'[Output repaired file]:file:_files' \\
                        '(-p --password)'{-p,--password}'[Password]:password:' \\
                        '1:archive:_files -g "*.apx"'
                    ;;
                benchmark|b)
                    _arguments \\
                        '--max-sample-mb[Max sample size in MB]:mb:' \\
                        '1:file:_files'
                    ;;
                info|i)
                    _arguments \\
                        '1:file:_files'
                    ;;
                completions)
                    _arguments \\
                        '1:shell:(bash zsh fish)'
                    ;;
            esac
            ;;
    esac
}

_apex "$@"
"""

FISH_COMPLETION = """# Apex CLI Fish completion

function __fish_apex_needs_command
    set cmd (commandline -opc)
    if [ (count $cmd) -eq 1 ]
        return 0
    end
    return 1
end

function __fish_apex_using_command
    set cmd (commandline -opc)
    if [ (count $cmd) -gt 1 ]
        if [ $cmd[2] = $argv[1] ]
            return 0
        end
    end
    return 1
end

# Commands
complete -f -c apex -n '__fish_apex_needs_command' -a compress -d 'Compress file or directory into .apx'
complete -f -c apex -n '__fish_apex_needs_command' -a c -d 'Compress alias'
complete -f -c apex -n '__fish_apex_needs_command' -a decompress -d 'Decompress .apx archive'
complete -f -c apex -n '__fish_apex_needs_command' -a x -d 'Decompress alias'
complete -f -c apex -n '__fish_apex_needs_command' -a extract -d 'Decompress alias'
complete -f -c apex -n '__fish_apex_needs_command' -a diff -d 'Compare two .apx archives'
complete -f -c apex -n '__fish_apex_needs_command' -a d -d 'Diff alias'
complete -f -c apex -n '__fish_apex_needs_command' -a test -d 'Test archive integrity'
complete -f -c apex -n '__fish_apex_needs_command' -a t -d 'Test alias'
complete -f -c apex -n '__fish_apex_needs_command' -a list -d 'List archive contents'
complete -f -c apex -n '__fish_apex_needs_command' -a l -d 'List alias'
complete -f -c apex -n '__fish_apex_needs_command' -a repair -d 'Self-heal damaged archive'
complete -f -c apex -n '__fish_apex_needs_command' -a fix -d 'Repair alias'
complete -f -c apex -n '__fish_apex_needs_command' -a benchmark -d 'Shootout benchmark'
complete -f -c apex -n '__fish_apex_needs_command' -a b -d 'Benchmark alias'
complete -f -c apex -n '__fish_apex_needs_command' -a info -d 'Entropy and compressibility analysis'
complete -f -c apex -n '__fish_apex_needs_command' -a i -d 'Info alias'
complete -f -c apex -n '__fish_apex_needs_command' -a completions -d 'Generate shell completions'

# Global flags
complete -c apex -s V -l version -d 'Show version'
complete -c apex -s h -l help -d 'Show help'

# Subcommand completions
complete -c apex -n '__fish_apex_using_command compress' -s m -l mode -a 'fast balanced ultra brute' -d 'Compression preset'
complete -c apex -n '__fish_apex_using_command compress' -s o -l output -r -d 'Output file'
complete -c apex -n '__fish_apex_using_command compress' -s r -l recovery -d 'Reed-Solomon recovery records'
complete -c apex -n '__fish_apex_using_command compress' -l cdc -d 'Content-Defined Chunking'

complete -c apex -n '__fish_apex_using_command decompress' -s d -l dest -r -d 'Destination directory'
complete -c apex -n '__fish_apex_using_command decompress' -s i -l include -r -d 'Include pattern for selective extraction'

complete -c apex -n '__fish_apex_using_command diff' -l json -d 'Output diff as JSON'

complete -c apex -n '__fish_apex_using_command completions' -a 'bash zsh fish' -d 'Shell type'
"""


def generate_completions(shell: str) -> str:
    """Returns shell completion script for the requested shell."""
    shell = shell.lower().strip()
    if shell == "bash":
        return BASH_COMPLETION
    elif shell == "zsh":
        return ZSH_COMPLETION
    elif shell == "fish":
        return FISH_COMPLETION
    else:
        raise ValueError(f"Unsupported shell: '{shell}'. Supported shells: bash, zsh, fish")
