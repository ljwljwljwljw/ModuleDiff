import os


class Module:
    def __init__(self, name):
        self.name = name
        self.ports = []

    def __str__(self):
        s = self.name
        s += "\n"
        for p in self.ports:
            s += str(p) + "\n"
        return s


class Port:
    def __init__(self, width, name, direction):
        self.direction = direction
        self.name = name
        self.width = width

    def __str__(self):
        return f"""{self.direction} {self.name} {self.width}"""


def parse_port(line: str, direction):
    words = line.split()
    width = 1
    port_list = []
    # print(words)
    if len(words) == 2:
        name = words[1].replace(',', '').replace('\n', '')
        port_list.append(Port(width, name, direction))
    else:
        width = int(words[1].replace('[', '').replace(']', '').split(':')[0]) + 1
        for elem in words[2:]:
            name = elem.replace(',', '').replace('\n', '')
            port_list.append(Port(width, name, direction))
    return port_list


def parser_file(file, design):
    with open(file, 'r') as f:
        module = None
        for line in f.readlines():
            if line.startswith("module") and (design in line):
                name = line.split()[1].replace('(', '').replace('\n', '')
                module = Module(name)
            if module is not None:
                if "input" in line:
                    ports = parse_port(line, "input")
                    module.ports += ports
                elif "output" in line:
                    ports = parse_port(line, "output")
                    module.ports += ports
                if line.startswith("endmodule"):
                    return module
        return module


def check_ports(mod1, mod2):
    pass


def creat_wrapper(f_raw, f_repl, design):
    mod_raw = parser_file(f_raw, design)
    assert mod_raw is not None
    mod_repl = parser_file(f_repl, design)
    assert mod_repl is not None
    check_ports(mod_raw, mod_repl)
    s = f"module {design}(\n"
    # create ports
    s += f"    output test_eq,\n"
    in_ports = []
    for p in mod_raw.ports:
        if p.direction == "input":
            in_ports.append(p)
    for i, p in enumerate(in_ports):
        if p.width == 1:
            if i == len(in_ports) - 1:
                s += f"    input {p.name}\n"
            else:
                s += f"    input {p.name},\n"
        else:
            if i == len(in_ports) - 1:
                s += f"    input [{str(p.width - 1)}:0] {p.name}\n"
            else:
                s += f"    input [{str(p.width - 1)}:0] {p.name},\n"
    s += ");\n"
    # create output wires
    out_ports = []
    for p in mod_raw.ports:
        if p.direction == "output":
            out_ports.append(p)
            if p.width == 1:
                s += f"    wire {p.name}_raw;\n"
                s += f"    wire {p.name}_repl;\n"
            else:
                s += f"    wire [{str(p.width - 1)}:0] {p.name}_raw;\n"
                s += f"    wire [{str(p.width - 1)}:0] {p.name}_repl;\n"
    # instantiate submodules
    s += f"{design}_raw raw_mod(\n"
    for i, p in enumerate(mod_raw.ports):
        postfix = ",\n" if i != len(mod_raw.ports) - 1 else "\n"
        if p.direction == "input":
            s += f"    .{p.name}({p.name})" + postfix
        else:
            s += f"    .{p.name}({p.name}_raw)" + postfix
    s += f");\n"

    s += f"{design}_repl repl_mod(\n"
    for i, p in enumerate(mod_repl.ports):
        postfix = ",\n" if i != len(mod_raw.ports) - 1 else "\n"
        if p.direction == "input":
            s += f"    .{p.name}({p.name})" + postfix
        else:
            s += f"    .{p.name}({p.name}_repl)" + postfix
    s += f");\n"
    # make comparison
    for p in out_ports:
        s += f"    wire {p.name}_eq;\n"
    for p in out_ports:
        s += f"    assign {p.name}_eq = {p.name}_raw == {p.name}_repl;\n"
    s += f"    assign test_eq = "
    for i in range(len(out_ports)):
        if i == 0:
            s += f"{out_ports[i].name}_eq"
        else:
            s += f" &&\n        {out_ports[i].name}_eq"
    s += ";\n"
    # endmodule
    s += "endmodule\n"
    return s


def cpp_main(file, design):
    mod = parser_file(file, design)
    stimulation = ""
    for p in mod.ports:
        if p.direction == "input" and p.name != "clock":
            tpe = ""
            if p.width <= 8:
                tpe = "(uint8_t)"
            elif p.width <= 16:
                tpe = "(uint16_t)"
            elif p.width <= 32:
                tpe = "(uint32_t)"
            if p.width < 64:
                stimulation += f"        dut_ptr->{p.name} = {tpe}(rand() % {pow(2, p.width)});\n"
            else:
                stimulation += f"        dut_ptr->{p.name} = {tpe}rand();\n"
    lim = 1000
    cpp = f"""
#include "verilated.h"
#include "V{design}.h"
#if VM_TRACE == 1
#include "verilated_vcd_c.h"
#endif
#include <iostream>
#include <fstream>
#include <cstdint>
#include <cstdlib>

int main() {{
    V{design}* dut_ptr = new V{design};
#if VM_TRACE == 1
    VerilatedVcdC* tfp = new VerilatedVcdC;
    Verilated::traceEverOn(true);
    dut_ptr->trace(tfp, 99);
    tfp->open("obj_dir/tmp.vcd");
#endif
    uint64_t limit = {str(lim)};
    uint64_t sim_time = 0;
    uint64_t err_cnt = 0;

    // reset
    // test
    while(sim_time < limit) {{
{stimulation}
        dut_ptr->clock = 0;
        dut_ptr->eval();
#if VM_TRACE == 1
        tfp->dump(sim_time);
#endif
        if(dut_ptr->test_eq != 1){{
            err_cnt++;
        }}
        sim_time++;
        dut_ptr->clock = 1;
        dut_ptr->eval();
    }}
    
    if(err_cnt != 0){{
        std::ofstream my_file("error.txt");
        my_file.close();
    }} else {{
        std::ofstream my_file("pass.txt");
        my_file.close();
    }}

    return err_cnt == 0 ? 0 : -1;
}}
    """
    return cpp


def create_makefile(design):
    text = f"""
VSRC = $(shell find . -name "*.v")
default: $(VSRC)
\tverilator -cc -exe main.cpp $^  --top-module {design} --build --trace -Wno-WIDTH -Wno-CMPCONST -Wno-REDEFMACRO --timescale-override 1ps/1ps
\t./obj_dir/V{design}
    """
    return text


def diff(f_raw, f_repl, design):
    work_dir = "./" + design
    os.system(f"rm -rf {work_dir}")
    os.system(f"mkdir {work_dir}")
    raw_path = f"{work_dir}/{design}_raw.v"
    repl_path = f"{work_dir}/{design}_repl.v"
    os.system(f"cp {f_raw} {raw_path}")
    os.system(f"cp {f_repl} {repl_path}")
    os.system(f"cp {repl_base}/*.v {work_dir}/")
    #os.system(f"cp {repl_base}/../sram/fast_func/*.v {work_dir}/")
    os.system(f"""sed -i "s/module.*{design}.*(/module {design}_raw(/g" {raw_path}""")
    os.system(f"""sed -i "s/module.*{design}.*(/module {design}_repl(/g" {repl_path}""")
    wrapper = creat_wrapper(raw_path, repl_path, design)
    with open(f"{work_dir}/{design}.v", "w") as f:
        f.write(wrapper)
    with open(f"{work_dir}/main.cpp", "w") as f:
        cpp = cpp_main(f"{work_dir}/{design}.v", design)
        f.write(cpp)
    with open(f"{work_dir}/Makefile", "w") as f:
        mk = create_makefile(design)
        f.write(mk)


repl_base = "/nfs/home/linjiawei/xs_nh_release/lib/regfile/"
raw_base = "/nfs/home/linjiawei/xs_nh_release/rtl/XSTop/"
if __name__ == '__main__':
    rf = "/home/lin/Documents/xs_nh_release/regfile/Regfile.v"
    lst = [
        "MaskedSyncDataModuleTemplate",
        "Regfile_1",
        "Regfile",
        "RenameTable_1",
        "RenameTable",
        "SQAddrModule_1",
        "SQAddrModule",
        "SyncDataModuleTemplate_10",
        "SyncDataModuleTemplate_1",
        "SyncDataModuleTemplate_2",
        "SyncDataModuleTemplate_3",
        "SyncDataModuleTemplate_4",
        "SyncDataModuleTemplate_5",
        "SyncDataModuleTemplate_6",
        "SyncDataModuleTemplate_7",
        "SyncDataModuleTemplate_8",
        "SyncDataModuleTemplate_9",
        "SyncDataModuleTemplate",
        "SyncRawDataModuleTemplate_10",
        "SyncRawDataModuleTemplate_4",
        "SyncRawDataModuleTemplate_6",
        "SyncRawDataModuleTemplate"
    ]
    make_str = ""
    targets = ""
    for design in lst:
        repl = repl_base + design + ".v"
        raw = raw_base + design + ".v"
        diff(raw, repl, design)
        make_str += f"{design}:\n\t-$(MAKE) -C ./{design}\n"
        targets += f"{design} "
    make_str += f"\n.PHONY: {targets}\nall: {targets}\nclean:\n\trm -rf {targets}\n"

    with open("./Makefile", "w") as f:
        f.write(make_str)

