"""
Parse Cucumber feature files into RobotFramework test script and resource

Resource will only be created if it does not exist.

Usage:
    gherkin2robotframework <feature> [output dir]


Author: Maurice Koster
Url: https://github.com/mauricekoster/gherkin2robotframework
License: See LICENSE


"""
import glob

from gherkin.parser import Parser
import os
import re
import argparse
import fnmatch
from datetime import datetime

from pprint import pprint

from .translation import get_language, tr, set_language

# - Globals -------------------------------------------------------------------

FIELD_SEP = "    "
settings_lines = []
test_cases_lines = []
keywords_lines = []
seen_steps = {}

background_available = None
settings_dir = ""
verbose = False


# - Functions -----------------------------------------------------------------


def process_gherkin(gherkin_filename, basedir, output):
    global settings_lines, test_cases_lines, keywords_lines, seen_steps

    print(f"Processing gherkin: {gherkin_filename}")
    if verbose:
        print(f"Basedir: {basedir}")
        print(f"Output: {output}")

    with open(gherkin_filename, 'r') as f:
        content = f.read()
    parser = Parser()
    gherkin = parser.parse(content)
    if gherkin is None:
        raise RuntimeError(f"Syntax error in file: {gherkin_filename}")

    settings_lines = []
    test_cases_lines = []
    keywords_lines = []
    seen_steps = {}

    feature = gherkin['feature']
    process_feature(feature)

    feature_base = os.path.dirname(gherkin_filename)
    feature_sub = None
    if feature_base.startswith(basedir):
        feature_sub = feature_base[len(basedir)+1:]
    else:
        feature_sub = feature_base

    generate_robot_script(os.path.join(output, feature_sub), feature['name'])


def write_to_script(outfile, line):
    if type(line) is list:
        outfile.write(FIELD_SEP.join(line) + '\n')
    else:
        outfile.write(line + '\n')


def _apply_settings(outfile, filename):
    for fn in [os.path.join(settings_dir, filename),
               os.path.join(os.getcwd(), filename)]:
        if os.path.exists(fn):
            if verbose:
                print(f"Apply extra settings: {fn}")
            with open(fn) as settings:
                lines = settings.readlines()
                outfile.writelines(lines)
                outfile.write('\n')
            return


def apply_feature_settings(outfile):
    _apply_settings(outfile, 'feature.settings')


def apply_resource_settings(outfile):
    _apply_settings(outfile, 'resource.settings')


def generate_robot_script(path, feature_name):
    if not os.path.exists(path):
        os.makedirs(path)

    step_definitions_resource = f"{feature_name}_step_definitions.resource"
    step_definitions_resource = step_definitions_resource.lower().replace(' ', '_')

    fn = feature_name.lower().replace(' ', '_') + '.robot'
    with open(os.path.join(path, fn), 'w') as outfile:
        if get_language() != "en":
            write_to_script(outfile, f'Language: {get_language()}\n' )
        write_to_script(outfile, tr('settings_section'))
        apply_feature_settings(outfile)
        for line in settings_lines:
            write_to_script(outfile, line)
        # Added ./ as workaround for RobotFramework plugin IntelliJ/PyCharm
        write_to_script(outfile, [tr("resource"), './' + step_definitions_resource])
        write_to_script(outfile, [tr("metadata"), 'Feature', feature_name])
        write_to_script(outfile, [tr("metadata"), 'Generated by', 
                                  '_gherkin2robotframework on {0}_'.format(datetime.now().isoformat())])
        write_to_script(outfile, '')

        write_to_script(outfile, tr("testcases_section"))
        for line in test_cases_lines:
            write_to_script(outfile, line)
        write_to_script(outfile, '')

        if keywords_lines:
            write_to_script(outfile, tr("keywords_section"))
            for line in keywords_lines:
                write_to_script(outfile, line)
            write_to_script(outfile, '')

    generate_robot_script_resource(path, step_definitions_resource)


def _read_keywords_from_resource(fn):
    lines = None
    keywords = []

    with open(fn, 'r') as f:
        lines = f.readlines()

    in_keywords = False
    for line in lines:
        if not line.strip():
            continue

        if in_keywords:
            if not line.startswith(' ') and not line.startswith('\t'):
                keyword = line.strip()
                kw = re.sub(r'\$\{[0-9a-zA-Z_]+\}', '(.*)', keyword)

                keywords.append((keyword,kw))
        else:
            if line.startswith('*** Keywords ***') or line.startswith(tr("keywords_section")):
                in_keywords = True

    if verbose:
        pprint(keywords)
    return keywords


def generate_robot_script_resource(path, step_definitions_resource):
    fn = os.path.join(path, step_definitions_resource)
    if os.path.exists(fn):
        if verbose:
            print(f"existing file {step_definitions_resource}")
        kw = _read_keywords_from_resource(fn)
        found = False
        for keyword, argument in seen_steps.items():
            ff = False
            for keyword_tuple in kw:
                keyword_org, keyword_regex = keyword_tuple
                if keyword == keyword_org:
                    ff = True
                else:
                    regex = re.compile(keyword_regex)
                    if re.match(regex, keyword):
                        ff = True
            if not ff:
                found = True
        if found:
            print(f"\nMissing keywords for: {fn}\n")
            for keyword, argument in seen_steps.items():
                ff = False
                for keyword_tuple in kw:
                    keyword_org, keyword_regex = keyword_tuple
                    if keyword == keyword_org:
                        ff = True
                    else:
                        regex = re.compile(keyword_regex)
                        if re.match(regex, keyword):
                            ff = True
                if not ff:
                    print(keyword)
                    if argument:
                        args = ['', f"[{tr('arguments')}]", argument]
                        print(FIELD_SEP.join(args))

                    args = ['', 'Fail', f'Keyword "{keyword}" Not Implemented Yet']
                    print(FIELD_SEP.join(args))
            print("\n")
    else:
        if verbose:
            print(f"new file {step_definitions_resource}")
        with open(fn, 'w') as f:
            if get_language() != "en":
                write_to_script(f, f'Language: {get_language()}\n' )
            write_to_script(f, tr('settings_section'))
            apply_resource_settings(f)
            write_to_script(f, [tr("documentation"), 'Generated by', 
                                '_gherkin2robotframework on {0}_'.format(datetime.now().isoformat())])
            write_to_script(f, [tr("library"), 'Collections'])
            write_to_script(f, '\n' + tr('keywords_section'))
            for k, v in seen_steps.items():
                write_to_script(f, k)
                if v:
                    args = ['', f'[{tr("arguments")}]', v]
                    write_to_script(f, args)
                args = ['', 'Fail', f'Keyword "{k}" Not Implemented Yet']
                write_to_script(f, args)
                write_to_script(f, '')

    if verbose:
        pprint(seen_steps)


def process_feature(feature):
    # pprint(feature)

    global background_available
    background_available = False
    if 'language' in feature:
        set_language(feature['language'])

    if 'description' in feature:
        description = feature['description'].strip().split('\n')
        settings_lines.append([tr('documentation'), description[0]])
        for doc in description[1:]:
            settings_lines.append(['...', doc])

    if feature['tags']:
        tags_list = [tr('testtags')]
        for tag in feature['tags']:
            tags_list.append(tag['name'][1:])
        settings_lines.append(tags_list)

    for child in feature['children']:

        if 'background' in child:
            process_background(child['background'])

        elif 'scenario' in child:
            process_scenario(child['scenario'])

        else:
            raise RuntimeError(f"Unimplemented child {','.join(child.keys())}")
            

def process_background(background):
    global background_available
    background_available = True

    keywords_lines.append(tr('background'))
    if background['name']:
        keywords_lines.append(['', f'[{tr("documentation")}]', background['name']])

    for step in background['steps']:
        add_step(keywords_lines, step)
    keywords_lines.append('')


def process_scenario(scenario):
    if scenario['keyword'] in ['Scenario'] + tr('scenario').split(','):
        process_scenario_plain(scenario)
    elif scenario['keyword'] in ['Scenario Outline'] + tr('scenariooutline').split(','):
        process_scenario_outline(scenario)
    else:
        raise RuntimeError(f"Unimplemented scenario keyword: {scenario['keyword']}")

def process_datatable_rows(datatable):
    ret = []
    for row in datatable:
        line = []
        for cell in row['cells']:
            line.append(cell['value'])
        ret.append(line)
    return ret


def generate_datatable_as_list_of_dict(output, dt):
    # FOR    ${BSN}   ${NAME}  IN
    # ...     1      Jan
    # ...     2      Piet
    # ...     3      Klaas
    #     ${entry}=        Create Dictionary    BSN=${BSN}   NAME=${NAME}
    #     Append To List  ${datatable}  ${entry}
    # END  

    output.append(['', '${DataTable}=', 'Create List'])
    # FOR
    line = ['', 'FOR']
    for col in dt[0]:
        line.append('${' + col + '}')
    line.append('IN')
    output.append(line)
    # IN     
    for row in dt[1:]:
        line = ['', '...']
        line.extend(row)
        output.append(line)

    # Create dictionary
    line = ['', '', '${entry}=', 'Create Dictionary']
    for col in dt[0]:
        line.append(col + '=${' + col + '}')
    output.append(line)

    # Append To List
    output.append(['', '', 'Append To List', '${DataTable}', '${entry}'])

    # END  (new syntax)
    output.append(['', 'END'])
    return '@{DataTable}'


def process_docstring(output, docstring):
    output.append(['', '${DocString}=', 'Catenate', 'SEPARATOR=\\n'])
    content = docstring['content'].split('\n')
    for line in content:
        if line:
            output.append(['', '...', line])
        else:
            output.append(['', '...', '${EMPTY}'])
    return '${DocString}'

def process_datatable(output, datatable):
    dt = process_datatable_rows(datatable['rows'])
    variablename = generate_datatable_as_list_of_dict(output, dt)
    return variablename



def add_step(output, step):
    text = step['text'].replace('<', '${').replace('>', '}')
    if step['keyword'] == '* ':
        keyword = text
        resource_keyword = text
    else:
        resource_keyword = text
        keyword = tr(step['keyword'], step['keyword']) + text

    argument_variable = None
    if 'docString' in step:
        argument_variable = process_docstring(output, step['docString'])
    elif 'dataTable' in step:
        argument_variable = process_datatable(output, step['dataTable'])        

    if resource_keyword not in seen_steps:
        seen_steps[resource_keyword] = argument_variable
    if argument_variable:
        output.append(['', keyword, argument_variable])
    else:
        output.append(['', keyword])


def process_tags(tags):
    tags_list = ['', f'[{tr("tags")}]']
    for tag in tags:
        tags_list.append(tag['name'][1:])
    test_cases_lines.append(tags_list)


def process_scenario_plain(scenario):
    test_cases_lines.append(scenario['name'])
    if 'description' in scenario:
        _add_test_case_documentation(scenario['description'])

    if scenario['tags']:
        process_tags(scenario['tags'])

    if background_available:
        test_cases_lines.append(['', tr('background')])
    for step in scenario['steps']:
        add_step(test_cases_lines, step)
    test_cases_lines.append('')


def make_empty(x):
    if x == '':
        return '${EMPTY}'
    else:
        return x


def _add_test_case_documentation(description):
    if not description:
        return
    
    _description = description.strip().split('\n')

    test_cases_lines.append(['', f'[{tr("documentation")}]', _description[0]])
    for doc in _description[1:]:
        test_cases_lines.append(['', '...', doc.strip()])


def _add_keyword_documentation(description):
    if not description:
        return

    _description = description.strip().split('\n')
    keywords_lines.append(['', f'[{tr("documentation")}]', _description[0]])
    for doc in _description[1:]:
        keywords_lines.append(['', '...', doc.strip()])


def process_scenario_outline(scenario):
    # collect variables in steps
    variables = []
    for step in scenario['steps']:
        v = re.findall('<([a-zA-Z0-9]+)>', step['text'])
        variables += v
    variables = set(variables)

    # per example a test case
    # for example in scenario['examples']:
    #     if example['name']:
    #         test_case_name = scenario['name'] + ': ' + example['name']
    #     else:
    #         test_case_name = scenario['name'] + ' example line ' + str(example['location']['line'])

    for example in scenario['examples']:
        if example['name']:
            test_case_name = scenario['name'] + ': ' + example['name']
        else:
            test_case_name = scenario['name'] + ' example line ' + str(example['location']['line'])

        # test_cases_lines.append(test_case_name)

        if 'description' in example:
            _add_test_case_documentation(example['description'])

        tags = []
        if scenario['tags']:
            tags.extend(scenario['tags'])
        if example['tags']:
            tags.extend(example['tags'])
        if tags:
            process_tags(tags)

        test_cases_lines.append(['', f'[{tr("template")}]', tr("scenariooutline").split(',')[0] + ' ' + scenario['name']])

        header_col = {}
        header = []
        col_nr = 0

        for header_cell in example['tableHeader']['cells']:
            v = header_cell['value']
            header_col[v] = col_nr
            header.append(v)
            col_nr += 1

        for v in variables:
            if v not in header:
                raise RuntimeWarning(f"Example {example['name']} missing column {v}")

        for example_row in example['tableBody']:
            args = []
            for a in header:
                args.append(example_row['cells'][header_col[a]]['value'])

            args = [''] + [make_empty(x) for x in args]
            test_cases_lines.append(args)

        test_cases_lines.append('')

    # Test Template
    keywords_lines.append(tr("scenariooutline").split(',')[0] + ' ' + scenario['name'])
    if 'description' in scenario:
        _add_keyword_documentation(scenario['description'])

    arguments = ['${' + arg + '}' for arg in header]
    keywords_lines.append(['', f'[{tr("arguments")}]'] + arguments)
    if background_available:
        keywords_lines.append(['', tr('background')])
    for step in scenario['steps']:
        add_step(keywords_lines, step)
    keywords_lines.append('')


def get_feature_filenames(feature_basedir):
    matches = []
    for root, _, filenames in os.walk(feature_basedir):
        for filename in fnmatch.filter(filenames, '*.feature'):
            matches.append(os.path.join(root, filename))
    return matches


def process_directory(d, output_dir):
    l = get_feature_filenames(d)
    for f in l:
        process_gherkin(f, d, output_dir)

# --------------------------------------------------------------------------------------
# Main part
# --------------------------------------------------------------------------------------


def determine_settings_dir(start_dir):
    global settings_dir
    settings_dir = start_dir
    d = start_dir
    t = None
    while d and not glob.glob(os.path.join(d, '*.settings')):
        d, t = os.path.split(d)
        if not t:
            break
    if t:
        # print "Settings dir: " + d
        settings_dir = d


def main():
    global verbose
    # - Commandline parsing -------------------------------------------------------

    cmdline_parser = argparse.ArgumentParser()
    cmdline_parser.add_argument("-v", "--verbose", action="store_true")
    cmdline_parser.add_argument("feature", nargs="?", default="")
    cmdline_parser.add_argument("output", nargs="?", default=None)
    cmdline_args = cmdline_parser.parse_args()
    verbose = cmdline_args.verbose

    if cmdline_args.feature:
        if os.path.isdir(cmdline_args.feature):
            # glob
            d = os.path.abspath(cmdline_args.feature)
            if cmdline_args.output:
                o = os.path.abspath(cmdline_args.output)
            else:
                o = d
            determine_settings_dir(d)
            process_directory(d, o)
        else:
            f = os.path.abspath(cmdline_args.feature)
            if cmdline_args.output:
                o = os.path.abspath(cmdline_args.output)
            else:
                o = os.path.dirname(f)
            determine_settings_dir(os.path.dirname(f))
            process_gherkin(f, os.path.dirname(f), o)
    else:
        determine_settings_dir(os.path.abspath('..'))
        process_directory(os.path.abspath('..'), os.path.abspath('..'))


if __name__ == '__main__':
    main()
