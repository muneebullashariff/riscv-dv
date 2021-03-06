"""
Copyright 2019 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Compare the instruction trace CSV
"""
import re
import argparse

from riscv_trace_csv import *

def compare_trace_csv(csv1, csv2, name1, name2,
                      in_order_mode, coalescing_limit, verbose,
                      mismatch_print_limit, compare_final_value_only):
  """Compare two trace CSV file"""
  matched_cnt = 0
  mismatch_cnt = 0

  with open(csv1, "r") as fd1, open(csv2, "r") as fd2:
    instr_trace_1 = []
    instr_trace_2 = []
    trace_csv_1 = RiscvInstructiontTraceCsv(fd1)
    trace_csv_2 = RiscvInstructiontTraceCsv(fd2)
    trace_csv_1.read_trace(instr_trace_1)
    trace_csv_2.read_trace(instr_trace_2)
    trace_1_index = 0
    trace_2_index = 0
    mismatch_cnt = 0
    matched_cnt = 0
    if in_order_mode:
      gpr_val_1 = {}
      gpr_val_2 = {}
      for trace in instr_trace_1:
        trace_1_index += 1
        # Check if there's a GPR change caused by this instruction
        gpr_state_change_1 = check_update_gpr(trace.rd, trace.rd_val, gpr_val_1)
        if gpr_state_change_1 == 0:
          continue
        # Move forward the other trace until a GPR update happens
        gpr_state_change_2 = 0
        while (gpr_state_change_2 == 0 and trace_2_index < len(instr_trace_2)):
          gpr_state_change_2 = check_update_gpr(
                               instr_trace_2[trace_2_index].rd,
                               instr_trace_2[trace_2_index].rd_val,
                               gpr_val_2)
          trace_2_index += 1
        # Check if the GPR update is the same between trace 1 and 2
        if gpr_state_change_2 == 0:
          mismatch_cnt += 1
          print("Mismatch[%d]:\n[%d] %s : %s" %
                (mismatch_cnt, trace_1_index, name1, trace.get_trace_string()))
          print ("%0d instructions left in trace %0s" %
                 (len(instr_trace_1) - trace_1_index + 1, name1))
        elif (trace.rd != instr_trace_2[trace_2_index-1].rd or
              trace.rd_val != instr_trace_2[trace_2_index-1].rd_val):
          mismatch_cnt += 1
          # print first few mismatches
          if mismatch_cnt <= mismatch_print_limit:
            print("Mismatch[%d]:\n%s[%d] : %s" %
                  (mismatch_cnt, name1, trace_2_index - 1,
                   trace.get_trace_string()))
            print("%s[%d] : %s" %
                  (name2, trace_2_index - 1,
                   instr_trace_2[trace_2_index-1].get_trace_string()))
        else:
          matched_cnt += 1
        # Break the loop if it reaches the end of trace 2
        if trace_2_index == len(instr_trace_2):
          break
      # Check if there's remaining instruction that change architectural state
      if trace_2_index != len(instr_trace_2):
        while (trace_2_index < len(instr_trace_2)):
          gpr_state_change_2 = check_update_gpr(
                               instr_trace_2[trace_2_index].rd,
                               instr_trace_2[trace_2_index].rd_val,
                               gpr_val_2)
          if gpr_state_change_2 == 1:
            print ("%0d instructions left in trace %0s" %
                  (len(instr_trace_2) - trace_2_index, name2))
            mismatch_cnt += len(instr_trace_2) - trace_2_index
            break
          trace_2_index += 1
    else:
      # For processors which can commit multiple instructions in one cycle, the
      # ordering between different GPR update on that cycle could be
      # non-deterministic. If multiple instructions try to update the same GPR on
      # the same cycle, these updates could be coalesced to one update.
      gpr_trace_1 = {}
      gpr_trace_2 = {}
      parse_gpr_update_from_trace(instr_trace_1, gpr_trace_1)
      parse_gpr_update_from_trace(instr_trace_2, gpr_trace_2)
      if len(gpr_trace_1) != len(gpr_trace_2):
        print("Mismatch: affected GPR count mismtach %s:%d VS %s:%d" %
              (name1, len(gpr_trace_1), name2, len(gpr_trace_2)))
        mismatch_cnt += 1
      if not compare_final_value_only:
        for gpr in gpr_trace_1:
          coalesced_updates = 0
          if (len(gpr_trace_1[gpr]) != len(gpr_trace_2[gpr]) and
              coalescing_limit == 0):
            print("Mismatch: GPR[%s] trace count mismtach %s:%d VS %s:%d" %
                  (gpr, name1, len(gpr_trace_1[gpr]),
                   name2, len(gpr_trace_2[gpr])))
            mismatch_cnt += 1
          trace_2_index = 0
          coalesced_updates = 0
          for trace_1_index in range(0, len(gpr_trace_1[gpr])-1):
            if (trace_2_index == len(gpr_trace_2[gpr])):
              break
            if long(gpr_trace_1[gpr][trace_1_index].rd_val, 16) != \
               long(gpr_trace_2[gpr][trace_2_index].rd_val, 16):
              if coalesced_updates >= coalescing_limit:
                coalesced_updates = 0
                mismatch_cnt += 1
                if mismatch_cnt <= mismatch_print_limit:
                  print("Mismatch:")
                  print("%s[%d] : %s" % (name1, trace_1_index,
                        gpr_trace_1[gpr][trace_1_index].get_trace_string()))
                  print("%s[%d] : %s" % (name2, trace_2_index,
                        gpr_trace_2[gpr][trace_2_index].get_trace_string()))
                trace_2_index += 1
              else:
                if verbose:
                  print("Skipping %s[%d] : %s" %
                        (name1, trace_1_index,
                         gpr_trace_1[gpr][trace_1_index].get_trace_string()))
                coalesced_updates += 1
            else:
              coalesced_updates = 0
              matched_cnt += 1
              if verbose:
                print("Matched [%0d]: %s : %s" %
                      (trace_1_index, name1,
                       gpr_trace_1[gpr][trace_1_index].get_trace_string()))
              trace_2_index += 1
      # Check the final value match between the two traces
      for gpr in gpr_trace_1:
        if (len(gpr_trace_1[gpr]) == 0 or len(gpr_trace_2[gpr]) == 0):
          mismatch_cnt += 1
          print("Zero GPR[%s] updates observed: %s:%d, %s:%d" % (gpr,
                name1, len(gpr_trace_1[gpr]), name2, len(gpr_trace_2[gpr])))
        elif long(gpr_trace_1[gpr][-1].rd_val, 16) != \
             long(gpr_trace_2[gpr][-1].rd_val, 16):
          mismatch_cnt += 1
          if mismatch_cnt <= mismatch_print_limit:
            print("Mismatch final value:")
            print("%s : %s" % (name1, gpr_trace_1[gpr][-1].get_trace_string()))
            print("%s : %s" % (name2, gpr_trace_2[gpr][-1].get_trace_string()))
    if mismatch_cnt == 0:
      compare_result = "PASSED"
    else:
      compare_result = "FAILED"
    print("Compare result[%s]: %d matched, %d mismatch" %
          (compare_result, matched_cnt, mismatch_cnt))


def parse_gpr_update_from_trace(trace_csv, gpr_trace):
  prev_val = {}
  for trace in trace_csv:
    if not (trace.rd in prev_val):
      gpr_trace[trace.rd] = []
      gpr_trace[trace.rd].append(trace)
    elif prev_val[trace.rd] != trace.rd_val:
      gpr_trace[trace.rd].append(trace)
    prev_val[trace.rd] = trace.rd_val


def check_update_gpr(rd, rd_val, gpr):
  gpr_state_change = 0
  if rd in gpr:
    if rd_val != gpr[rd]:
      gpr_state_change = 1
  else:
    if int(rd_val, 16) != 0:
      gpr_state_change = 1
  gpr[rd] = rd_val
  return gpr_state_change


# Parse input arguments
parser = argparse.ArgumentParser()
parser.add_argument("csv_file_1", type=str, help="Instruction trace 1 CSV")
parser.add_argument("csv_file_2", type=str, help="Instruction trace 2 CSV")
parser.add_argument("csv_name_1", type=str, help="Instruction trace 1 name")
parser.add_argument("csv_name_2", type=str, help="Instruction trace 2 name")
# optional arguments
parser.add_argument("--in_order_mode", type=int, default=1,
                    help="In order comparison mode")
parser.add_argument("--gpr_update_coalescing_limit", type=int, default=1,
                    help="Allow the core to merge multiple updates to the \
                          same GPR into one. This option only applies to \
                          trace 2")
parser.add_argument("--mismatch_print_limit", type=int, default=5,
                    help="Max number of mismatches printed")
parser.add_argument("--verbose", type=int, default=0,
                    help="Verbose logging")
parser.add_argument("--compare_final_value_only", type=int, default=0,
                    help="Only compare the final value of the GPR")

args = parser.parse_args()

if args.compare_final_value_only:
  args.in_order_mode = 0

# Compare trace CSV
compare_trace_csv(args.csv_file_1, args.csv_file_2,
                  args.csv_name_1, args.csv_name_2,
                  args.in_order_mode, args.gpr_update_coalescing_limit,
                  args.verbose, args.mismatch_print_limit,
                  args.compare_final_value_only)
