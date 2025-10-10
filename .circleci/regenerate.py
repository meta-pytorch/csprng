import os 
import yaml
from jinja2 import Environment, FileSystemLoader

PYTHON_VERSIONS = ["3.6","3.7", "3.8", "3.9"]
OS_TYPES = ["linux", "macos","win"]
BUILD_TYPES = ["wheel", "conda"]

CUDA_MATRIX = {
    "linux": ["cpu", "cu101", "cu102", "cu111"],
    "win":  ["cpu", "cu101", "cu102", "cu111"],
    "macos": ["cpu"],
}

RC_PATTERN = r"/v[0-9]+(\.[0-9]+)*-rc[0-9]+/"

def gen_filter_branch_tree(*branches, tags_list=None):
    # Use single item for single branch, list for multiple branches
    branches_output = branches[0] if len(branches) == 1 else [b for b in branches]
    
    filter_dict = {"branches": {"only": branches_output}}
    if tags_list is not None:
        filter_dict["tags"] = {"only": tags_list}
    return filter_dict


def build_workflows(indentation=6):
    jobs = []

    for btype in BUILD_TYPES:
        for os_type in OS_TYPES:
            for python_version in PYTHON_VERSIONS:
                # Skip macOS conda py3.9 until conda-forge has compatible packages
                if os_type == "macos" and btype == "conda" and python_version == "3.9":
                        continue                          
                for cu_version in CUDA_MATRIX[os_type]:

                    job_name = f"binary_{os_type}_{btype}_py{python_version}_{cu_version}"
                    
                    job = {
                        "cu_version": cu_version,
                        "name": job_name,
                        "python_version": python_version,
                        "wheel_docker_image": get_manylinux_image(cu_version),
                    }
                    
                    if os_type == 'win':
                        if python_version in ["3.6", "3.7"] :
                            job = {
                                "cu_version": cu_version,
                                "filters" : gen_filter_branch_tree("master", tags_list=RC_PATTERN),
                                "name": job_name,
                                "python_version": python_version,
                            }
                        elif python_version in ["3.8","3.9"] and cu_version in ["cu101", "cu102"]:
                            job = {
                                    "cu_version": cu_version,
                                    "filters": gen_filter_branch_tree("master", tags_list=RC_PATTERN),
                                    "name": job_name,
                                    "python_version": python_version,
                                }
                        else:
                            job = {
                                "cu_version": cu_version,
                                "name": job_name,
                                "python_version": python_version,
                            }

                            
                    jobs.append({f"binary_{os_type}_{btype}": job})

    return indent(indentation, jobs)

def unittest_workflows(indentation=6):
    jobs = []
    for os_type in ["linux", "windows", "macos"]:    
        for device_type in ['cpu', "gpu"]:
            if os_type == "macos" and device_type == "gpu":
                continue
            for python_version in PYTHON_VERSIONS:
                    if os_type in ["linux", "macos"] and device_type == "cpu" and python_version == "3.9":
                        continue
                    
                    job= {
                        "cu_version": 'cpu' if device_type == "cpu" else 'cu101',
                        "name": f"unittest_{os_type}_{device_type}_py{python_version}",
                        "python_version" : python_version,
                    }
    
                    if device_type == 'gpu' and python_version in ['3.6','3.7']:
                        job= {
                        "cu_version": "cu101",
                        "filters" :  gen_filter_branch_tree("master", "nightly"),
                        "name": f"unittest_{os_type}_{device_type}_py{python_version}",
                        "python_version" : python_version,
                        }
                   
                        
                    jobs.append({f"unittest_{os_type}_{device_type}":job})
                                                
    return indent(indentation,jobs)

manylinux_images = {
    "cu101": "pytorch/manylinux-cuda101",
    "cu102": "pytorch/manylinux-cuda102",
    "cu110": "pytorch/manylinux-cuda110",
    "cu111": "pytorch/manylinux-cuda111",
    "cu112": "pytorch/manylinux-cuda112",
}


def get_manylinux_image(cu_version):
    if cu_version == "cpu":
        return "pytorch/manylinux-cuda102"
    elif cu_version.startswith('cu'):
        cu_suffix = cu_version[len('cu'):]
        return f"pytorch/manylinux-cuda{cu_suffix}"

def nightly_workflows(indentation=6):
    jobs = []
    for btype in BUILD_TYPES:
        for os_type in OS_TYPES:
            for python_version in PYTHON_VERSIONS:
                if os_type == "macos" and btype == "conda" and python_version ==  "3.9":
                    continue
                for cu_version in CUDA_MATRIX[os_type]:

                    base_workflow_name = f"nightly_binary_{os_type}_{btype}_py{python_version}_{cu_version}"
                        
                    build_job = {
                        "cu_version": cu_version,
                        "filters": gen_filter_branch_tree("nightly", tags_list=RC_PATTERN),
                        "name": base_workflow_name,
                        "python_version": python_version,
                        "wheel_docker_image": get_manylinux_image(cu_version),
                        }
                    if os_type == "win" and btype == "conda":
                        build_job = {
                            "cu_version": cu_version,
                            "filters": gen_filter_branch_tree("nightly", tags_list=RC_PATTERN),
                            "name": base_workflow_name,
                            "python_version": python_version,
                        }

                    upload_job_name = f"{base_workflow_name}_upload"

                    upload_job = {                
                        "context": "org-member",
                        "filters": gen_filter_branch_tree("nightly", tags_list=RC_PATTERN),
                        "name": upload_job_name,
                        "requires": [base_workflow_name],
                        }

                    if btype == 'wheel':
                        upload_job["subfolder"] = "" if os_type == 'macos' else cu_version + "/"
                    

                    jobs.append({f"binary_{os_type}_{btype}": build_job})
                    jobs.append({f"binary_{btype}_upload": upload_job})
   
    return indent(indentation, jobs)

def indent(indentation, data_list):
    import yaml
    from io import StringIO

    class MyDumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super(MyDumper, self).increase_indent(flow, False)

    stream = StringIO()
    yaml.dump(
        data_list,
        stream,
        Dumper=MyDumper,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        width=1000,
    )

    yaml_str = stream.getvalue()
    lines = yaml_str.splitlines()

    # Apply indentation, skip truly empty lines
    indented_lines = []
    for line in lines:
        if line.strip():  # Only indent non-empty lines
            indented_lines.append(' ' * indentation + line)
        else:
            indented_lines.append('')  # Keep empty lines as-is

    return '\n'.join(indented_lines) + '\n'

if __name__ == "__main__":
    d = os.path.dirname(__file__)
    env = Environment(
        loader=FileSystemLoader(d),
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    
    with open(os.path.join(d, 'config.yml'), 'w') as f:
            f.write(env.get_template('config.yml.in').render(
                build_workflows=build_workflows,
                unittest_workflows=unittest_workflows,
                nightly_workflows=nightly_workflows
            ))





