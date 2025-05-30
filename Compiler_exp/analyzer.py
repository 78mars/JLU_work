# analyzer.py

from enum import Enum
from Lexer import Lexer, Token 
from ASTparser import Parser as ASTParser, TreeNode, generate_ast_from_source, format_ast_to_display_string

# --- 1. Enums ---
class TypeKind(Enum):
    INTEGER = "integer"; CHAR = "char"; BOOLEAN = "boolean"; ARRAY = "array"
    RECORD = "record"; ALIAS = "alias"; PROC = "procedure"; PROGRAM = "program"
    UNKNOWN = "unknown"

class SymbKind(Enum):
    TYPE = "typekind"; VARIABLE = "varkind"; PROCEDURE = "prockind"
    PARAMETER_VALUE = "valparamkind"; PARAMETER_VAR = "varparamkind"
    PROGRAM = "programkind"; FIELD = "fieldkind"

class AccessKind(Enum):
    VALUE = "access_value"; ADDRESS = "access_address"

# --- 2. TypeIR and subclasses ---
class TypeIR:
    def __init__(self, kind: TypeKind, initial_size: int = 0):
        self.kind = kind; self._size = initial_size
    @property
    def size(self) -> int: return self._size
    def get_base_type(self) -> 'TypeIR': return self
    def __str__(self): return f"Type(kind={self.kind.value}, size={self.size})"
    def __eq__(self, other):
        if not isinstance(other, TypeIR): return NotImplemented
        return self.get_base_type().kind == other.get_base_type().kind

class IntegerIR(TypeIR):
    def __init__(self): super().__init__(TypeKind.INTEGER, 1)#构造函数指出类型和大小
class CharIR(TypeIR):
    def __init__(self): super().__init__(TypeKind.CHAR, 1)
class BooleanIR(TypeIR):
    def __init__(self): super().__init__(TypeKind.BOOLEAN, 1)

class AliasIR(TypeIR):
    def __init__(self, alias_name: str, actual_type: TypeIR):
        super().__init__(TypeKind.ALIAS)
        self.alias_name = alias_name
        self.actual_type = actual_type if actual_type is not None else TypeIR(TypeKind.UNKNOWN)
    @property
    def size(self) -> int: return self.actual_type.size
    def get_base_type(self) -> TypeIR: return self.actual_type.get_base_type()
    def __str__(self): return f"Alias(name={self.alias_name} -> {str(self.actual_type)}) (size: {self.size})"
    def __eq__(self, other):
        if not isinstance(other, TypeIR): return NotImplemented
        return self.get_base_type().__eq__(other.get_base_type())

class ArrayIR(TypeIR):
    def __init__(self, index_low: int, index_high: int, element_type: TypeIR):
        super().__init__(TypeKind.ARRAY)
        self.index_low = index_low; self.index_high = index_high; self.element_type = element_type
        if self.element_type is None or self.element_type.kind == TypeKind.UNKNOWN or index_high < index_low:
            self._size = 0
        else:
            self._size = ((index_high - index_low) + 1) * self.element_type.size
    def __str__(self): return f"Array[{self.index_low}..{self.index_high}] of {str(self.element_type) if self.element_type else 'None'}"
    def __eq__(self, other):
        if not isinstance(other, TypeIR): return NotImplemented
        base_self = self.get_base_type(); base_other = other.get_base_type()
        if not isinstance(base_self, ArrayIR) or not isinstance(base_other, ArrayIR): return base_self.kind == base_other.kind
        return base_self.index_low == base_other.index_low and \
               base_self.index_high == base_other.index_high and \
               base_self.element_type == base_other.element_type

class RecordIR(TypeIR):
    def __init__(self):
        super().__init__(TypeKind.RECORD); self.fields: dict[str, dict[str, TypeIR | int]] = {}
        self._current_field_offset = 0; self._size = 0
    def add_field(self, name: str, field_type: TypeIR) -> bool:
        if name in self.fields or field_type is None or field_type.kind == TypeKind.UNKNOWN: return False
        self.fields[name] = {'type': field_type, 'offset': self._current_field_offset}
        self._current_field_offset += field_type.size; self._size = self._current_field_offset; return True
    def get_field_type(self, name: str) -> TypeIR | None:
        field_data = self.fields.get(name); return field_data['type'] if field_data else None # type: ignore
    def get_field_offset(self, name: str) -> int | None:
        field_data = self.fields.get(name); return field_data['offset'] if field_data else None # type: ignore

    def __str__(self):
        field_strs = [f"{name}: {data['type']}@off:{data['offset']}" for name, data in self.fields.items()] # 显示字段偏移
        return f"Record({', '.join(field_strs)}) (size: {self.size})"
    def __eq__(self, other):#重写了父类的 __eq__ 方法。当比较一个 AliasIR 对象与其他类型是否相等时，它会比较两者解析到底层后的基本类型是否相等
        if not isinstance(other, TypeIR): return NotImplemented
        base_self = self.get_base_type(); base_other = other.get_base_type()
        if not isinstance(base_self, RecordIR) or not isinstance(base_other, RecordIR): return base_self.kind == base_other.kind
        if len(base_self.fields) != len(base_other.fields): return False
        for name, data in base_self.fields.items():
            other_field_data = base_other.fields.get(name)
            # 比较字段时也比较偏移量，确保结构完全一致
            if not other_field_data or data['type'] != other_field_data['type'] or data['offset'] != other_field_data['offset']:
                 return False
        return True

class ParamIR:
    def __init__(self, name: str, type_ir: TypeIR, is_var_param: bool):
        self.name = name; self.type_ir = type_ir; self.is_var_param = is_var_param
    def __str__(self): return f"Param(name='{self.name}', type={str(self.type_ir) if self.type_ir else 'None'}, var={self.is_var_param})"

class ProcIR(TypeIR):
    def __init__(self): super().__init__(TypeKind.PROC); self.params: list[ParamIR] = []
    def add_param(self, param_ir: ParamIR): self.params.append(param_ir)
    def __str__(self): return f"ProcType(params=[{', '.join(str(p) for p in self.params)}])"

# --- 3. SymbolTableEntry and SymbolTable ---
class SymbTableEntry:
    def __init__(self, name: str, kind: SymbKind, type_ir: TypeIR | None, level: int, offset: int = 0):
        self.name = name; self.kind = kind; self.type_ir = type_ir; self.level = level; self.offset = offset
        self.proc_params_ir: ProcIR | None = None
    def __str__(self):
        type_str = str(self.type_ir) if self.type_ir else "None"
        param_info = ""
        if self.kind == SymbKind.PROCEDURE and self.proc_params_ir:
            param_strs = [(f"var {p.name}: {p.type_ir}" if p.is_var_param else f"{p.name}: {p.type_ir}") for p in self.proc_params_ir.params]
            param_info = f" Params({', '.join(param_strs)})"
        # 调整 Type 字段宽度以容纳更长的类型字符串（如记录）
        return f"{self.name:<15} | {self.kind.value:<15} | {type_str:<60} | L{self.level:<3} | Offs {self.offset:<5}{param_info}"

class SymbolTable:
    def __init__(self):
        self.scopes: list[dict[str, SymbTableEntry]] = [{}]
        #一个整数，用于跟踪当前最内层（或最深）的词法作用域级别。初始值为0，代表全局作用域
        self.current_level = 0 
    def enter_scope(self): self.scopes.append({}); self.current_level += 1
    def exit_scope(self):
        if self.current_level > 0: self.scopes.pop(); self.current_level -= 1
    def insert(self, name: str, kind: SymbKind, type_ir: TypeIR | None, offset: int = 0) -> SymbTableEntry | None:
        current_scope = self.scopes[-1]
        if name in current_scope: return None
        entry = SymbTableEntry(name, kind, type_ir, self.current_level, offset); current_scope[name] = entry
        return entry
    def find(self, name: str) -> SymbTableEntry | None:
        for level in range(self.current_level, -1, -1):
            if name in self.scopes[level]: return self.scopes[level][name]
        return None
    def find_in_current_scope(self, name: str) -> SymbTableEntry | None: return self.scopes[-1].get(name)
    def get_all_entries(self) -> list[SymbTableEntry]:
        all_entries = []
        for scope_dict in self.scopes:
            for entry in scope_dict.values(): all_entries.append(entry)
        return all_entries

# --- 4. SemanticAnalyzer ---
class SemanticAnalyzer:
    def __init__(self, trace_to_console=False):
        self.symbol_table = SymbolTable()
        self.trace_to_console = trace_to_console
        self.errors: list[str] = []
        self.listing_for_file: list[str] = []

        # 用于跟踪当前作用域的下一个可用偏移量。栈结构，对应符号表的作用域。
        self.scope_offsets_stack: list[int] = [0] # 全局作用域 (level 0) 的偏移量从0开始

        self.current_procedure_entry: SymbTableEntry | None = None
        self.TYPE_INTEGER = IntegerIR(); self.TYPE_CHAR = CharIR()
        self.TYPE_BOOLEAN = BooleanIR(); self.TYPE_UNKNOWN = TypeIR(TypeKind.UNKNOWN)
        self._initialize_predefined_types()

    def _get_current_offset_and_advance(self, item_size: int) -> int:
        """获取当前作用域的当前偏移量，并将其增加 item_size。"""
        if not self.scope_offsets_stack:
            self._log_error("内部错误: 作用域偏移量栈为空。")
            return -1 # 表示错误
        #获取栈顶元素，即当前最内层作用域的下一个可用偏移量。这个 current_offset 将被赋给当前正在声明的符号
        current_offset = self.scope_offsets_stack[-1]
        if item_size < 0 : #不应该发生
             self._log_error(f"内部错误: 尝试分配负大小 {item_size}。")
             item_size = 0 # 避免负增长
        self.scope_offsets_stack[-1] += item_size#将栈顶元素增加，下一个在该作用域声明的符号就会得到更新后的偏移量
        return current_offset #返回分配给当前符号的偏移量

    def _log_error(self, message: str, node: TreeNode | None = None):
        node_info = ""; full_message = f"语义错误: {message}"
        if node and hasattr(node, 'node_type'):
            node_info = f" (AST节点: {node.node_type}{f' value: {node.value}' if node.value else ''})"
            full_message += node_info
        self.errors.append(full_message)
        self.listing_for_file.append(f"错误: {full_message}")

    def analyze(self, root_node: TreeNode | None) -> tuple[list[SymbTableEntry], list[str], list[str]]:
        self.errors = []; self.listing_for_file = ["--- 开始语义分析 ---"]
        # 每次新的分析开始时，重置偏移量栈，只保留全局作用域的初始偏移量 (通常是0)
        # 如果之前分析过，self.scope_offsets_stack[0] 可能不是0，这里确保从0开始新的全局偏移计算
        self.scope_offsets_stack = [0]


        if not isinstance(root_node, TreeNode) or root_node.node_type != "ProK":
            self._log_error("根节点不是有效的 ProK TreeNode 或为 None。", root_node)
            self.listing_for_file.append("语义分析因无效根节点而中止。")
            return self.symbol_table.get_all_entries(), self.errors, self.listing_for_file

        if root_node.children and isinstance(root_node.children[0], TreeNode) and root_node.children[0].node_type == "PheadK":
            program_head_node = root_node.children[0]
            program_name = getattr(program_head_node, 'value', None)
            if program_name and isinstance(program_name, str):
                # 程序名本身不占用由 scope_offsets_stack[0] 管理的数据区偏移量
                entry = self.symbol_table.insert(program_name, SymbKind.PROGRAM, TypeIR(TypeKind.PROGRAM), offset=0)
                if entry: self.listing_for_file.append(f"程序名 '{program_name}' 已处理: {str(entry)}")
            else: self._log_error("PheadK 节点缺少有效的程序名 (value)。", program_head_node)
        else: self._log_error("ProK 节点缺少有效的 PheadK 子节点。", root_node)

        self._traverse_node(root_node)

        if self.trace_to_console: self._print_symbol_table_to_console("最终符号表状态 (控制台)")
        self._add_symbol_table_snapshot_to_listing("最终符号表状态 (文件日志)")

        self.listing_for_file.append(f"\n--- 语义分析完成 ---")
        if self.errors: self.listing_for_file.append(f"共发现 {len(self.errors)} 个语义错误:")
        else: self.listing_for_file.append("语义分析成功完成 (无错误)。")

        if self.trace_to_console and self.errors:
            print("\n---语义分析错误汇总 (控制台) ---")
            for err_msg in self.errors: print(err_msg)

        return self.symbol_table.get_all_entries(), self.errors, self.listing_for_file

    def _traverse_node(self, node: TreeNode | None):
        if node is None: return
        if not isinstance(node, TreeNode) or not hasattr(node, 'node_type'):
            self._log_error(f"遍历时遇到无效节点: {node}"); return
        handler_name = f"_handle_{node.node_type.lower()}"
        handler = getattr(self, handler_name, self._handle_unknown_node)
        try: handler(node)
        except Exception as e:
            self._log_error(f"处理节点 {node.node_type} 时发生内部错误: {e}", node)
            import traceback
            self.listing_for_file.append(f"处理节点 {node.node_type} 时内部错误: {traceback.format_exc()}")

    def _initialize_predefined_types(self):
        # 预定义类型不消耗数据区偏移量，它们的偏移量为0是合适的
        entry_int = self.symbol_table.insert("integer", SymbKind.TYPE, self.TYPE_INTEGER, offset=0)
        entry_char = self.symbol_table.insert("char", SymbKind.TYPE, self.TYPE_CHAR, offset=0)
        entry_bool = self.symbol_table.insert("boolean", SymbKind.TYPE, self.TYPE_BOOLEAN, offset=0)
        if entry_int: self.listing_for_file.append(f"预定义类型: {str(entry_int)}")
        if entry_char: self.listing_for_file.append(f"预定义类型: {str(entry_char)}")
        if entry_bool: self.listing_for_file.append(f"预定义类型: {str(entry_bool)}")

    def _handle_unknown_node(self, node: TreeNode):
        for child in node.children: self._traverse_node(child)

    def _handle_prok(self, node: TreeNode):
        for child in node.children:
            if child.node_type != "PheadK": self._traverse_node(child)

    def _handle_typek(self, node: TreeNode):
        self.listing_for_file.append(f"分析类型声明 (TypeK)...")
        for type_dec_node in node.children:
            if not isinstance(type_dec_node, TreeNode) or type_dec_node.node_type != "DecK":
                self._log_error(f"TypeK 中遇到非预期的子节点: {type_dec_node}", node); continue
            alias_name = type_dec_node.value
            if not isinstance(alias_name, str): self._log_error(f"类型声明 DecK value 不是字符串", type_dec_node); continue
            if self.symbol_table.find_in_current_scope(alias_name):
                self._log_error(f"类型 '{alias_name}' 重复声明。", type_dec_node); continue
            if not type_dec_node.children or not isinstance(type_dec_node.children[0], TreeNode):
                self._log_error(f"类型声明 '{alias_name}' 缺少类型结构或子节点无效。", type_dec_node); continue
            actual_type_ast_node = type_dec_node.children[0]
            type_ir = self._process_type_node(actual_type_ast_node)
            if type_ir and type_ir.kind != TypeKind.UNKNOWN:
                aliased_type_ir = AliasIR(alias_name, type_ir)
                # 类型声明本身不消耗数据偏移量
                entry = self.symbol_table.insert(alias_name, SymbKind.TYPE, aliased_type_ir, offset=0)
                if entry: self.listing_for_file.append(f"  已声明类型别名: {str(entry)}")
            else: self._log_error(f"无法解析类型声明 '{alias_name}'。", actual_type_ast_node)
        if self.trace_to_console: self._print_symbol_table_to_console("类型声明之后 (控制台)")
        self._add_symbol_table_snapshot_to_listing("类型声明之后 (文件日志)")

    def _process_type_node(self, type_ast_node: TreeNode | None) -> TypeIR:
        if not isinstance(type_ast_node, TreeNode) or not hasattr(type_ast_node, 'node_type'):
            self._log_error("处理类型节点时遇到无效节点或 None。", type_ast_node); return self.TYPE_UNKNOWN
        node_type = type_ast_node.node_type
        if node_type == "IntegerK": return self.TYPE_INTEGER
        elif node_type == "CharK": return self.TYPE_CHAR
        elif node_type == "IdK": return self._name_type(type_ast_node)
        elif node_type == "ArrayK": return self._array_type(type_ast_node)
        elif node_type == "RecordK": return self._record_type(type_ast_node)
        else: self._log_error(f"未知的AST节点用于类型处理: {node_type}", type_ast_node); return self.TYPE_UNKNOWN

    def _name_type(self, id_node: TreeNode) -> TypeIR:
        type_name = id_node.value
        if not isinstance(type_name, str): self._log_error(f"IdK 类型节点 value 不是字符串", id_node); return self.TYPE_UNKNOWN
        entry = self.symbol_table.find(type_name)
        if not entry: self._log_error(f"类型 '{type_name}' 未声明。", id_node); return self.TYPE_UNKNOWN
        if entry.kind != SymbKind.TYPE: self._log_error(f"标识符 '{type_name}' 不是一个类型。", id_node); return self.TYPE_UNKNOWN
        if entry.type_ir is None: self._log_error(f"类型 '{type_name}' 的内部表示为 None。", id_node); return self.TYPE_UNKNOWN
        return entry.type_ir

    def _array_type(self, array_k_node: TreeNode) -> TypeIR:
        if len(array_k_node.children) != 3:
            self._log_error("ArrayK 结构无效 (期望3个子节点: low, high, elem_type)。", array_k_node); return self.TYPE_UNKNOWN
        low_node, high_node, element_type_node = array_k_node.children
        low_val, high_val = -1, -1
        try:
            val_node_value = getattr(low_node, 'value', None)
            if getattr(low_node, 'node_type', None) == "ExpK" and isinstance(val_node_value, str) and val_node_value.startswith("Const "): low_val = int(val_node_value.split(" ")[1])
            elif isinstance(val_node_value, int): low_val = val_node_value
            else: self._log_error(f"无法提取数组低界或格式错误", low_node); return self.TYPE_UNKNOWN

            val_node_value = getattr(high_node, 'value', None)
            if getattr(high_node, 'node_type', None) == "ExpK" and isinstance(val_node_value, str) and val_node_value.startswith("Const "): high_val = int(val_node_value.split(" ")[1])
            elif isinstance(val_node_value, int): high_val = val_node_value
            else: self._log_error(f"无法提取数组高界或格式错误", high_node); return self.TYPE_UNKNOWN

            if low_val > high_val: self._log_error(f"数组低界 {low_val} > 高界 {high_val}。", array_k_node); return self.TYPE_UNKNOWN
        except ValueError: self._log_error(f"数组界限值无法转换为整数。", array_k_node); return self.TYPE_UNKNOWN
        except Exception as e: self._log_error(f"处理数组界限时AST结构错误或意外错误: {e}", array_k_node); return self.TYPE_UNKNOWN

        element_type_ir = self._process_type_node(element_type_node)
        if element_type_ir is None or element_type_ir.kind == TypeKind.UNKNOWN:
            self._log_error(f"数组元素类型未知。", element_type_node); return self.TYPE_UNKNOWN
        return ArrayIR(low_val, high_val, element_type_ir)

    def _record_type(self, record_k_node: TreeNode) -> TypeIR:
        record_ir = RecordIR()
        self.symbol_table.enter_scope()
        self.scope_offsets_stack.append(0) # 为记录字段的临时作用域压入偏移量计数器 (虽然主要用RecordIR内部偏移)
        self.listing_for_file.append(f"  进入记录定义作用域 (层次 {self.symbol_table.current_level})")

        for field_dec_node in record_k_node.children:
            if not isinstance(field_dec_node, TreeNode) or field_dec_node.node_type != "DecK":
                self._log_error(f"RecordK 中非预期子节点: {field_dec_node}", record_k_node); continue
            field_name = field_dec_node.value
            if not isinstance(field_name, str): self._log_error(f"记录域 DecK value 不是字符串", field_dec_node); continue
            if not field_dec_node.children or not isinstance(field_dec_node.children[0], TreeNode):
                self._log_error(f"记录域 '{field_name}' 缺少类型定义或子节点无效。", field_dec_node); continue

            field_type_ast_node = field_dec_node.children[0]
            field_type_ir = self._process_type_node(field_type_ast_node)

            if field_type_ir is None or field_type_ir.kind == TypeKind.UNKNOWN:
                self._log_error(f"域 '{field_name}' 类型未知。", field_type_ast_node); continue

            # add_field 会计算并存储字段在 RecordIR 内部的偏移量
            if not record_ir.add_field(field_name, field_type_ir):
                self._log_error(f"未能添加域名 '{field_name}' 到记录 (可能重复)。", field_dec_node)
            else:
                # 将字段插入临时符号表作用域，用于检查重名，其偏移量是字段在记录内部的偏移量
                field_offset_in_record = record_ir.get_field_offset(field_name)
                if field_offset_in_record is None: # 如果 add_field 成功，这里不应为 None
                    self._log_error(f"内部错误: 无法获取记录域 '{field_name}' 的偏移量", field_dec_node); continue

                if not self.symbol_table.insert(field_name, SymbKind.FIELD, field_type_ir, offset=field_offset_in_record):
                    self._log_error(f"记录域 '{field_name}' 在当前记录的临时作用域中重复。", field_dec_node)
                else:
                    self.listing_for_file.append(f"    已定义记录域: {field_name}: {field_type_ir} (在记录内偏移: {field_offset_in_record})")

        self.scope_offsets_stack.pop() # 退出记录字段的临时作用域
        self.symbol_table.exit_scope()
        self.listing_for_file.append(f"  退出记录定义作用域 (返回到层次 {self.symbol_table.current_level})")
        return record_ir

    def _handle_vark(self, node: TreeNode):
        self.listing_for_file.append(f"分析变量声明 (VarK)...")
        for var_dec_group_node in node.children:
            if not isinstance(var_dec_group_node, TreeNode) or var_dec_group_node.node_type != "DecK":
                self._log_error(f"VarK 中非预期子节点: {var_dec_group_node}", node); continue
            if not var_dec_group_node.children or not isinstance(var_dec_group_node.children[0], TreeNode):
                self._log_error("空变量声明组(DecK)或类型节点无效。", var_dec_group_node); continue

            type_ast_node = var_dec_group_node.children[0]
            var_type_ir = self._process_type_node(type_ast_node)

            if var_type_ir is None or var_type_ir.kind == TypeKind.UNKNOWN:
                self._log_error(f"不能用未知类型声明变量", type_ast_node); continue
            if var_type_ir.kind in [TypeKind.PROC, TypeKind.PROGRAM]:
                self._log_error(f"不能声明类型为 '{var_type_ir.kind.value}' 的变量。", type_ast_node); continue
            # 不允许声明大小为0的变量 (除非是别名指向有效类型，或未知类型导致的错误)
            if var_type_ir.size == 0 and var_type_ir.get_base_type().kind != TypeKind.UNKNOWN :
                 self._log_error(f"不能声明大小为0的类型 '{var_type_ir.kind.value}' 的变量。", type_ast_node); continue

            for i in range(1, len(var_dec_group_node.children)):
                var_id_node = var_dec_group_node.children[i]
                if not isinstance(var_id_node, TreeNode) or var_id_node.node_type != "IdK":
                    self._log_error(f"变量名预期为 IdK 类型节点", var_id_node); continue
                var_name = var_id_node.value
                if not isinstance(var_name, str): self._log_error(f"变量 IdK value 不是字符串", var_id_node); continue

                if self.symbol_table.find_in_current_scope(var_name):
                    self._log_error(f"变量 '{var_name}' 重复声明。", var_id_node)
                else:
                    var_offset = self._get_current_offset_and_advance(var_type_ir.size)
                    entry = self.symbol_table.insert(var_name, SymbKind.VARIABLE, var_type_ir, offset=var_offset)
                    if entry: self.listing_for_file.append(f"  已声明变量: {str(entry)}")

        if self.trace_to_console: self._print_symbol_table_to_console("变量声明之后 (控制台)")
        self._add_symbol_table_snapshot_to_listing("变量声明之后 (文件日志)")

    def _handle_procdeck(self, node: TreeNode):
        proc_name = node.value
        if not isinstance(proc_name, str): self._log_error(f"ProcDecK value (过程名) 不是字符串", node); return
        self.listing_for_file.append(f"分析过程声明: {proc_name}...")
        if self.symbol_table.find_in_current_scope(proc_name):
            self._log_error(f"过程 '{proc_name}' 在当前作用域重复声明。", node); return

        proc_signature_ir = ProcIR()
        # 过程声明本身不占用其父作用域的数据区偏移量，偏移量为0
        proc_entry = self.symbol_table.insert(proc_name, SymbKind.PROCEDURE, proc_signature_ir, offset=0)
        if not proc_entry: self._log_error(f"未能为过程 '{proc_name}' 创建符号表条目。", node); return

        proc_entry.proc_params_ir = proc_signature_ir
        self.listing_for_file.append(f"  已声明过程: {str(proc_entry)}")
        self.current_procedure_entry = proc_entry

        self.symbol_table.enter_scope()
        self.scope_offsets_stack.append(0) # 为过程的参数和局部变量创建一个新的偏移量上下文，从0开始
        self.listing_for_file.append(f"  进入过程 '{proc_name}' 作用域 (层次 {self.symbol_table.current_level}, 下一偏移量 {self.scope_offsets_stack[-1]})")

        param_list_k_node, local_type_k_node, local_var_k_node, body_stmlk_node = None, None, None, None
        for child in node.children:
            if not isinstance(child, TreeNode): continue
            if child.node_type == "ParamListK": param_list_k_node = child
            elif child.node_type == "TypeK": local_type_k_node = child # 局部类型声明
            elif child.node_type == "VarK": local_var_k_node = child  # 局部变量声明
            elif child.node_type == "StmLK": body_stmlk_node = child

        if param_list_k_node: self._handle_paramlistk(param_list_k_node, proc_signature_ir)
        # 参数处理后，记录符号表快照
        if self.trace_to_console: self._print_symbol_table_to_console(f"过程 {proc_name} 参数处理后 (控制台)")
        self._add_symbol_table_snapshot_to_listing(f"过程 {proc_name} 参数处理后 (文件日志)")
        
        # 处理局部类型声明 (不影响当前数据偏移量)
        if local_type_k_node: self._handle_typek(local_type_k_node)
        # 处理局部变量声明 (会使用并推进当前作用域的偏移量)
        if local_var_k_node: self._handle_vark(local_var_k_node)

        if body_stmlk_node: self._traverse_node(body_stmlk_node)
        else: self._log_error(f"过程 '{proc_name}' 缺少过程体 (StmLK)。", node)

        if self.trace_to_console: self._print_symbol_table_to_console(f"过程 {proc_name} 作用域结束前 (控制台)")
        self._add_symbol_table_snapshot_to_listing(f"过程 {proc_name} 作用域结束前 (文件日志)")

        self.scope_offsets_stack.pop() # 退出过程作用域，弹出其偏移量计数器
        self.symbol_table.exit_scope()
        self.listing_for_file.append(f"  退出过程 '{proc_name}' 作用域 (返回到层次 {self.symbol_table.current_level})")
        self.current_procedure_entry = None

    def _handle_paramlistk(self, node: TreeNode, proc_signature_ir: ProcIR):
        self.listing_for_file.append(f"  分析参数 (ParamListK)...")
        for param_dec_node in node.children:
            if not isinstance(param_dec_node, TreeNode) or param_dec_node.node_type != "DecK":
                self._log_error(f"ParamListK 中非预期子节点: {param_dec_node}", node); continue
            param_kind_str = param_dec_node.value
            if not isinstance(param_kind_str, str): self._log_error(f"参数 DecK value 不是字符串", param_dec_node); continue
            is_var_param = "var" in param_kind_str.lower()
            sym_kind = SymbKind.PARAMETER_VAR if is_var_param else SymbKind.PARAMETER_VALUE

            if len(param_dec_node.children) < 2 : # 至少一个类型节点和一个参数名节点
                self._log_error("参数 DecK 结构错误或子节点无效 (期望类型后至少一个参数名)。", param_dec_node); continue
            
            type_ast_node = param_dec_node.children[0]
            if not isinstance(type_ast_node, TreeNode):
                 self._log_error("参数 DecK 的类型子节点无效。", param_dec_node); continue
            param_type_ir = self._process_type_node(type_ast_node)

            if param_type_ir is None or param_type_ir.kind == TypeKind.UNKNOWN:
                self._log_error(f"参数类型未知。", type_ast_node); continue
            
            # 实际分配的大小：如果是 var 参数，通常是地址大小（例如1个字）。
            # 如果是值参数，是类型本身的大小。
            # 为简单起见，这里使用 param_type_ir.size。在更复杂的系统中，
            # var 参数的大小可能是固定的地址大小。
            # SNL 通常简单处理，这里我们假设 param_type_ir.size 已经是正确的分配大小。
            # 例如，integer (size 1), char (size 1). 如果 var integer a，a 在栈上可能仍占1个单位存地址。
            allocated_size = 1 if is_var_param and param_type_ir.size > 0 else param_type_ir.size # 简化：var参数占1个单位存地址
            if allocated_size == 0 and param_type_ir.get_base_type().kind != TypeKind.UNKNOWN:
                 self._log_error(f"不能声明大小为0的参数 (类型 '{param_type_ir.kind.value}')。", type_ast_node); continue


            for i in range(1, len(param_dec_node.children)):
                param_id_node = param_dec_node.children[i]
                if not isinstance(param_id_node, TreeNode) or param_id_node.node_type != "IdK":
                    self._log_error(f"参数名预期为 IdK 类型节点", param_id_node); continue
                param_name = param_id_node.value
                if not isinstance(param_name, str): self._log_error(f"参数 IdK value 不是字符串", param_id_node); continue

                if self.symbol_table.find_in_current_scope(param_name):
                    self._log_error(f"参数 '{param_name}' 重复声明。", param_id_node)
                else:
                    param_offset = self._get_current_offset_and_advance(allocated_size)
                    entry = self.symbol_table.insert(param_name, sym_kind, param_type_ir, offset=param_offset)
                    if entry:
                        self.listing_for_file.append(f"    已声明参数: {str(entry)}")
                        proc_signature_ir.add_param(ParamIR(param_name, param_type_ir, is_var_param))

    def _handle_stmlk(self, node: TreeNode):
        # (与之前代码相同)
        if not hasattr(node, 'children'):
            self.listing_for_file.append(f"警告: StmLK 节点 {node.value if node.value else ''} 没有 'children' 属性。")
            return
        for stmt_node_child in node.children:
            if not isinstance(stmt_node_child, TreeNode):
                self._log_error(f"StmLK 的一个子元素不是 TreeNode 类型: {type(stmt_node_child)}。", node)
                continue
            self._traverse_node(stmt_node_child)

    def _handle_stmtk(self, node: TreeNode):
        # (与之前代码相同)
        stmt_kind = node.value
        if not isinstance(stmt_kind, str): self._log_error(f"StmtK value (语句类型) 不是字符串", node); return
        if stmt_kind == "Assign": self._assign_statement(node)
        elif stmt_kind == "If": self._if_statement(node)
        elif stmt_kind == "Read": self._read_statement(node)
        elif stmt_kind == "Write": self._write_statement(node)
        elif stmt_kind == "Call": self._call_statement(node)
        else: self._log_error(f"未知语句类型: {stmt_kind}", node)

    def _expr(self, exp_node: TreeNode | None, access_kind_needed: AccessKind = AccessKind.VALUE) -> TypeIR:
        # (与之前代码相同, 但需要确保对 IdV 的处理能正确返回字段类型，如果支持 record.field 表达式)
        if not isinstance(exp_node, TreeNode) or not hasattr(exp_node, 'node_type'):
            self._log_error("表达式节点无效或为 None。", exp_node); return self.TYPE_UNKNOWN
        node_type = exp_node.node_type; node_val_str = exp_node.value
        if node_type != "ExpK": self._log_error(f"表达式预期为 ExpK, 实际为 {node_type}", exp_node); return self.TYPE_UNKNOWN
        if not isinstance(node_val_str, str): self._log_error(f"ExpK value 预期为字符串", exp_node); return self.TYPE_UNKNOWN
        parts = node_val_str.split(" ", 1)
        if not parts: self._log_error(f"ExpK value 格式错误 (空)", exp_node); return self.TYPE_UNKNOWN
        exp_kind_token = parts[0]

        if exp_kind_token == "Op":
            if len(parts) < 2: self._log_error(f"OpK value 格式错误 (缺操作符)", exp_node); return self.TYPE_UNKNOWN
            op_symbol = parts[1]
            if len(exp_node.children) == 2:
                left_type_ir = self._expr(exp_node.children[0]); right_type_ir = self._expr(exp_node.children[1])
                if left_type_ir.kind == TypeKind.UNKNOWN or right_type_ir.kind == TypeKind.UNKNOWN: return self.TYPE_UNKNOWN
                left_base_type = left_type_ir.get_base_type(); right_base_type = right_type_ir.get_base_type()
                if op_symbol in ['+', '-', '*', '/']:
                    if not (left_base_type.kind == TypeKind.INTEGER and right_base_type.kind == TypeKind.INTEGER):
                        self._log_error(f"算术运算 '{op_symbol}' 需整型操作数", exp_node); return self.TYPE_UNKNOWN
                    return self.TYPE_INTEGER
                elif op_symbol in ['<', '=']:
                    if left_base_type.kind != right_base_type.kind or \
                       left_base_type.kind not in [TypeKind.INTEGER, TypeKind.CHAR]:
                        self._log_error(f"比较运算 '{op_symbol}' 需同类型可比较操作数 (int,char)", exp_node); return self.TYPE_UNKNOWN
                    return self.TYPE_BOOLEAN
                else: self._log_error(f"未知二元操作符 '{op_symbol}'。", exp_node); return self.TYPE_UNKNOWN
            else: self._log_error(f"操作符 '{op_symbol}' 操作数数量不正确。", exp_node); return self.TYPE_UNKNOWN
        elif exp_kind_token == "IdV":
            if len(parts) < 2: self._log_error(f"IdV value 格式错误 (缺变量名)", exp_node); return self.TYPE_UNKNOWN
            var_name = parts[1]; entry = self.symbol_table.find(var_name)
            if not entry: self._log_error(f"变量 '{var_name}' 未声明。", exp_node); return self.TYPE_UNKNOWN
            # 字段 (FIELD) 通常在特定上下文中（如记录访问）才被视为变量，这里可能需要更复杂的逻辑
            # 如果 IdV 直接用于表示字段，那么它必须在记录访问的上下文中被限定
            if entry.kind not in [SymbKind.VARIABLE, SymbKind.PARAMETER_VALUE, SymbKind.PARAMETER_VAR, SymbKind.FIELD]:
                self._log_error(f"标识符 '{var_name}' 非变量/参数/域。", exp_node); return self.TYPE_UNKNOWN
            if access_kind_needed == AccessKind.ADDRESS and entry.kind == SymbKind.PARAMETER_VALUE:
                self._log_error(f"不能获取值参 '{var_name}' 地址。", exp_node) 
            if entry.type_ir is None: self._log_error(f"标识符 '{var_name}' 类型信息为 None。", exp_node); return self.TYPE_UNKNOWN
            return entry.type_ir
        elif exp_kind_token == "Const":
            if len(parts) < 2: self._log_error(f"ConstK value 格式错误 (缺常量值)", exp_node); return self.TYPE_UNKNOWN
            const_val_str = parts[1]
            try: int(const_val_str); return self.TYPE_INTEGER
            except ValueError: self._log_error(f"无效整数常量: {const_val_str}", exp_node); return self.TYPE_UNKNOWN
        elif exp_kind_token == "ArrayAccess": return self._array_var(exp_node, access_kind_needed)
        # TODO: 添加对记录字段访问表达式的处理 (例如 "RecordAccess", "FieldIdK" 等)
        # elif exp_kind_token == "RecordAccess": return self._record_field_access_expr(exp_node, access_kind_needed)
        else: self._log_error(f"未知表达式种类标记: {exp_kind_token}", exp_node); return self.TYPE_UNKNOWN

    def _array_var(self, access_node: TreeNode, access_kind_needed: AccessKind) -> TypeIR:
        # (与之前代码相同)
        if len(access_node.children) != 2: self._log_error("数组访问节点结构错误。", access_node); return self.TYPE_UNKNOWN
        array_base_node, index_expr_node = access_node.children[0], access_node.children[1]
        array_type_ir = self._expr(array_base_node, AccessKind.VALUE) 
        if array_type_ir.kind == TypeKind.UNKNOWN : return self.TYPE_UNKNOWN
        array_base_type = array_type_ir.get_base_type()
        if not isinstance(array_base_type, ArrayIR):
            var_name_in_error = getattr(array_base_node, 'value', "未知数组基").split(" ",1)[-1] if isinstance(getattr(array_base_node, 'value', ""),str) else "??"
            self._log_error(f"标识符 '{var_name_in_error}' 不是数组类型。", array_base_node); return self.TYPE_UNKNOWN
        index_type_ir = self._expr(index_expr_node)
        if index_type_ir.kind == TypeKind.UNKNOWN : return self.TYPE_UNKNOWN
        if index_type_ir.get_base_type().kind != TypeKind.INTEGER:
            self._log_error(f"数组下标需整型", index_expr_node); return self.TYPE_UNKNOWN
        if array_base_type.element_type is None:
            self._log_error(f"数组 '{var_name_in_error}' 元素类型为 None。", array_base_node); return self.TYPE_UNKNOWN
        return array_base_type.element_type

    def _assign_statement(self, assign_node: TreeNode):
        # (与之前代码相同)
        if len(assign_node.children) != 2: self._log_error("赋值语句结构错误。", assign_node); return
        lhs_node, rhs_node = assign_node.children[0], assign_node.children[1]
        lhs_type_ir = self._expr(lhs_node, AccessKind.ADDRESS)
        rhs_type_ir = self._expr(rhs_node, AccessKind.VALUE)
        if lhs_type_ir.kind == TypeKind.UNKNOWN or rhs_type_ir.kind == TypeKind.UNKNOWN: return
        lhs_base_type = lhs_type_ir.get_base_type(); rhs_base_type = rhs_type_ir.get_base_type()
        if lhs_base_type != rhs_base_type:
            self._log_error(f"赋值类型不匹配: 左侧 '{lhs_type_ir}' (基础 '{lhs_base_type}'), 右侧 '{rhs_type_ir}' (基础 '{rhs_base_type}')。", assign_node)

    def _call_statement(self, call_node: TreeNode):
        # (与之前代码相同)
        if not call_node.children or not isinstance(call_node.children[0], TreeNode) or call_node.children[0].node_type != "ProcIdK":
            self._log_error("过程调用结构错误(缺过程名 ProcIdK 或子节点无效)。", call_node); return
        proc_id_node = call_node.children[0]; proc_name = proc_id_node.value
        if not isinstance(proc_name, str): self._log_error(f"ProcIdK value (过程名)非字符串", proc_id_node); return
        proc_entry = self.symbol_table.find(proc_name)
        if not proc_entry: self._log_error(f"过程 '{proc_name}' 未声明。", proc_id_node); return
        if proc_entry.kind != SymbKind.PROCEDURE: self._log_error(f"标识符 '{proc_name}' 非过程。", proc_id_node); return
        formal_params_signature_ir = proc_entry.proc_params_ir
        if not formal_params_signature_ir or not hasattr(formal_params_signature_ir, 'params'): 
            self._log_error(f"内部错误: 过程 '{proc_name}' 缺参数签名结构。", proc_id_node); return
        formal_params = formal_params_signature_ir.params
        actual_arg_nodes = []
        if len(call_node.children) > 1 and isinstance(call_node.children[1], TreeNode) and call_node.children[1].node_type == "ArgListK":
            actual_arg_nodes = call_node.children[1].children
        if len(formal_params) != len(actual_arg_nodes):
            self._log_error(f"过程 '{proc_name}' 期望 {len(formal_params)} 个参数, 实际得到 {len(actual_arg_nodes)} 个。", call_node); return
        for i, formal_param in enumerate(formal_params):
            actual_arg_node = actual_arg_nodes[i]
            if not isinstance(actual_arg_node, TreeNode): self._log_error(f"过程 '{proc_name}' 第 {i+1} 实参节点无效。", call_node); continue
            access_needed = AccessKind.ADDRESS if formal_param.is_var_param else AccessKind.VALUE
            actual_arg_type_ir = self._expr(actual_arg_node, access_needed)
            if actual_arg_type_ir.kind == TypeKind.UNKNOWN: continue
            if formal_param.type_ir is None: self._log_error(f"内部错误: 形参 '{formal_param.name}' 类型信息为 None"); continue
            if formal_param.type_ir.get_base_type() != actual_arg_type_ir.get_base_type():
                self._log_error(f"过程 '{proc_name}' 第 {i+1} 参数类型不匹配。期望 '{formal_param.type_ir}', 得到 '{actual_arg_type_ir}'。", actual_arg_node)

    def _if_statement(self, if_node: TreeNode):
        # (与之前代码相同)
        if len(if_node.children) < 2 or \
           not isinstance(if_node.children[0], TreeNode) or \
           not isinstance(if_node.children[1], TreeNode): 
            self._log_error("If 语句结构错误或子节点无效。", if_node); return
        cond_expr_node, then_stmlk_node = if_node.children[0], if_node.children[1]
        cond_type_ir = self._expr(cond_expr_node)
        if cond_type_ir.kind == TypeKind.UNKNOWN : return
        if cond_type_ir.get_base_type().kind != TypeKind.BOOLEAN:
            self._log_error(f"If 条件需布尔型, 得到 {cond_type_ir}。", cond_expr_node)
        self._traverse_node(then_stmlk_node)
        if len(if_node.children) > 2:
            else_stmlk_node = if_node.children[2]
            if isinstance(else_stmlk_node, TreeNode): self._traverse_node(else_stmlk_node)
            elif else_stmlk_node is not None:
                   self._log_error("If else 分支节点无效 (非TreeNode)。", if_node)

    def _read_statement(self, read_node: TreeNode):
        # (与之前代码相同)
        if not read_node.children or not isinstance(read_node.children[0], TreeNode): 
            self._log_error("Read 语句结构错误(缺变量/子节点无效)。", read_node); return
        var_node_to_read = read_node.children[0]
        var_type_ir = self._expr(var_node_to_read, AccessKind.ADDRESS)
        if var_type_ir.kind == TypeKind.UNKNOWN: return
        base_var_type = var_type_ir.get_base_type()
        if base_var_type.kind not in [TypeKind.INTEGER, TypeKind.CHAR]:
            self._log_error(f"Read 不能读入类型 {var_type_ir} (基础类型 {base_var_type.kind.value})。需整型/字符型。", var_node_to_read)

    def _write_statement(self, write_node: TreeNode):
        # (与之前代码相同)
        if not write_node.children or not isinstance(write_node.children[0], TreeNode): 
            self._log_error("Write 语句结构错误(缺表达式/子节点无效)。", write_node); return
        expr_node_to_write = write_node.children[0]
        expr_type_ir = self._expr(expr_node_to_write, AccessKind.VALUE)
        if expr_type_ir.kind == TypeKind.UNKNOWN: return
        base_expr_type = expr_type_ir.get_base_type()
        if base_expr_type.kind not in [TypeKind.INTEGER, TypeKind.CHAR]:
            self._log_error(f"Write 不能输出类型 {expr_type_ir} (基础类型 {base_expr_type.kind.value})。需整型/字符型。", expr_node_to_write)

    def _add_symbol_table_snapshot_to_listing(self, title="符号表快照"):
        self.listing_for_file.append(f"\n--- {title} ---")
        for level, scope in enumerate(self.symbol_table.scopes):
            next_offset_info = "N/A"
            if level < len(self.scope_offsets_stack): # 确保不越界访问
                next_offset_info = str(self.scope_offsets_stack[level])
            self.listing_for_file.append(f"作用域层次: {level} (下一可用偏移: {next_offset_info})")
            if not scope: self.listing_for_file.append("  <空>"); continue
            for name, entry in scope.items(): self.listing_for_file.append(f"  {str(entry)}")
        self.listing_for_file.append(f"--- 快照结束 ({title}) ---\n")

    def _print_symbol_table_to_console(self, title="符号表快照 (控制台)"):
        print(f"\n--- {title} ---")
        for level, scope in enumerate(self.symbol_table.scopes):
            next_offset_info = "N/A"
            if level < len(self.scope_offsets_stack): # 确保不越界访问
                next_offset_info = str(self.scope_offsets_stack[level])
            print(f"作用域层次: {level} (下一可用偏移: {next_offset_info})")
            if not scope: print("  <空>"); continue
            for name, entry in scope.items(): print(f"  {str(entry)}")
        print(f"--- 快照结束 ({title}) ---")


# --- 5. 顶层函数和命令行测试 ---
def perform_semantic_analysis_from_source(source_code_string: str, trace_to_console_for_debug: bool = False) -> tuple[str, str, str, list[str]]:
    ast_string = "未能生成AST (可能由于词法或语法错误)。"
    symbol_table_string = "未能生成符号表 (可能由于前期错误或语义分析错误)。"
    error_messages_list: list[str] = []
    analysis_listing: list[str] = ["--- 开始完整分析流程 ---"]

    try:
        analysis_listing.append("\n--- 1. 词法分析与语法分析 (生成 AST) ---")
        # 这些函数需要从外部导入或在此处提供定义
        # from ASTparser import generate_ast_from_source, format_ast_to_display_string
        ast_root = generate_ast_from_source(source_code_string)
        ast_string = format_ast_to_display_string(ast_root)
        analysis_listing.append("词法及语法分析成功，AST已生成。")

        analysis_listing.append("\n--- 2. 语义分析 ---")
        analyzer = SemanticAnalyzer(trace_to_console=trace_to_console_for_debug)
        symbol_table_entries, semantic_errors, semantic_internal_listing = analyzer.analyze(ast_root)

        error_messages_list.extend(semantic_errors)
        analysis_listing.extend(semantic_internal_listing)

        if symbol_table_entries:
            # 根据 SymbTableEntry.__str__ 中 Type 字段宽度调整
            header = f"{'Name':<15} | {'Kind':<15} | {'Type':<60} | {'Lvl':<3} | {'Offset':<5} {'Params/Details'}\n"
            separator = "-" * (15 + 3 + 15 + 3 + 60 + 3 + 3 + 3 + 5 + 3 + 30) + "\n" # 调整分隔符长度
            table_str_list = [header, separator]
            for entry in symbol_table_entries:
                table_str_list.append(str(entry) + "\n")
            symbol_table_string = "".join(table_str_list)
        elif not error_messages_list:
            symbol_table_string = "符号表为空。"
            analysis_listing.append(symbol_table_string)

    except SyntaxError as se_syn: # 假设词法/语法分析可能抛出 SyntaxError
        err_msg = f"语法/词法分析错误:\n{str(se_syn)}"
        error_messages_list.append(err_msg)
        ast_string = f"AST生成失败: {str(se_syn)}"
        analysis_listing.append(err_msg)
    except ImportError:
        err_msg = "错误: 依赖的 Lexer 或 ASTparser 模块未能导入。"
        error_messages_list.append(err_msg)
        analysis_listing.append(err_msg)
    except Exception as e_other:
        err_msg = f"分析过程中发生意外错误:\n{str(e_other)}"
        error_messages_list.append(err_msg)
        ast_string = f"AST生成失败: {str(e_other)}"
        analysis_listing.append(err_msg)
        import traceback
        analysis_listing.append(traceback.format_exc())

    formatted_error_string = "\n".join(error_messages_list) if error_messages_list else "无错误报告。"
    analysis_listing.append("\n--- 完整分析流程结束 ---")

    return symbol_table_string, formatted_error_string, ast_string, analysis_listing

def read_snl_input():
    print("请输入 SNL 源程序 (连续两个空行结束输入):")
    lines = []; empty_line_consecutive_count = 0
    while True:
        try:
            line = input()
            if not line.strip():
                empty_line_consecutive_count += 1
                if empty_line_consecutive_count >= 2 and lines:
                    if lines and not lines[-1].strip(): lines.pop() # 移除末尾因两次回车多出的空行
                    break
                elif not lines and empty_line_consecutive_count >=1 : break # 允许只输入空行然后结束
            else: empty_line_consecutive_count = 0
            lines.append(line)
        except EOFError: break
    return "\n".join(lines)

def main_compiler_pipeline_cli():
    source_code = read_snl_input()
    if not source_code.strip(): print("错误: 未输入SNL源代码。"); return

    table_str, err_str, ast_str_output, full_listing = \
        perform_semantic_analysis_from_source(source_code, trace_to_console_for_debug=True)

    print("\n--- AST (来自语义分析流程) ---"); print(ast_str_output)
    print("\n--- 符号表 (来自语义分析流程) ---"); print(table_str)
    if err_str and err_str != "无错误报告。": print("\n--- 错误信息 ---"); print(err_str)
    else: print("\n--- 分析成功完成 (无错误报告) ---")

    if full_listing:
        print(f"\n(详细分析日志包含 {len(full_listing)} 行，将写入 listing.txt)")
        try:
            with open("listing.txt", "w", encoding="utf-8") as f_cli:
                for line_item in full_listing: f_cli.write(line_item + "\n")
            print("(详细分析日志已写入 listing.txt)")
        except IOError as e: print(f"\n写入 listing.txt 时发生错误: {e}")


# --- 模拟的外部依赖 (用于独立测试) ---
# 确保这些模拟定义在使用它们之前
if 'generate_ast_from_source' not in globals():
    def generate_ast_from_source(source_code_string: str) -> TreeNode | None:
        # print(f"MOCK: generate_ast_from_source called...")
        # 一个非常简单的模拟AST，用于测试偏移量
        # program p; var integer v1, v2; procedure q(integer i); var integer a; begin a:=i; end; begin read(v1); q(v1); end.
        phead = TreeNode("PheadK", value="p")

        # var integer v1, v2;
        vark_global = TreeNode("VarK")
        type_int_node1 = TreeNode("IntegerK")
        id_v1_node = TreeNode("IdK", value="v1")
        id_v2_node = TreeNode("IdK", value="v2")
        dec_v_node = TreeNode("DecK", children=[type_int_node1, id_v1_node, id_v2_node])
        vark_global.children.append(dec_v_node)
        
        # type tRec = record integer f1; char f2; end; var tRec r1;
        typek_global = TreeNode("TypeK")
        
        # Record type tRec
        id_tRec_node = TreeNode("IdK", value="tRec") # This is the DecK value for the type name
        recordk_node = TreeNode("RecordK")
        # field integer f1
        deck_f1 = TreeNode("DecK", value="f1", children=[TreeNode("IntegerK")])
        # field char f2
        deck_f2 = TreeNode("DecK", value="f2", children=[TreeNode("CharK")])
        recordk_node.children.extend([deck_f1, deck_f2])
        deck_tRec = TreeNode("DecK", value="tRec", children=[recordk_node])
        typek_global.children.append(deck_tRec)

        # var tRec r1;
        type_id_tRec_node = TreeNode("IdK", value="tRec") # Referring to the type tRec
        id_r1_node = TreeNode("IdK", value="r1")
        dec_r1_node = TreeNode("DecK", children=[type_id_tRec_node, id_r1_node])
        vark_global.children.append(dec_r1_node)


        # procedure q(integer i); var integer a; begin ... end;
        procdeck_q = TreeNode("ProcDecK", value="q")
        paramlist_q = TreeNode("ParamListK")
        type_int_node2 = TreeNode("IntegerK")
        id_i_node = TreeNode("IdK", value="i")
        dec_param_i_node = TreeNode("DecK", value="val", children=[type_int_node2, id_i_node]) # 'val' for value param
        paramlist_q.children.append(dec_param_i_node)

        vark_local_q = TreeNode("VarK")
        type_int_node3 = TreeNode("IntegerK")
        id_a_node = TreeNode("IdK", value="a")
        dec_var_a_node = TreeNode("DecK", children=[type_int_node3, id_a_node])
        vark_local_q.children.append(dec_var_a_node)
        
        stmlk_q_body = TreeNode("StmLK") # 简单赋值 a:=i
        assign_stmt = TreeNode("StmtK", value="Assign")
        assign_lhs = TreeNode("ExpK", value="IdV a") # 简化AST结构，实际解析器可能更复杂
        assign_rhs = TreeNode("ExpK", value="IdV i")
        assign_stmt.children.extend([assign_lhs, assign_rhs])
        stmlk_q_body.children.append(assign_stmt)

        procdeck_q.children.extend([paramlist_q, TreeNode("TypeK"), vark_local_q, stmlk_q_body]) # Empty local TypeK

        # Main program body
        stmlk_main = TreeNode("StmLK")
        read_stmt = TreeNode("StmtK", value="Read")
        read_var = TreeNode("ExpK", value="IdV v1")
        read_stmt.children.append(read_var)
        stmlk_main.children.append(read_stmt)
        
        call_stmt = TreeNode("StmtK", value="Call")
        call_proc_id = TreeNode("ProcIdK", value="q")
        call_arg_list = TreeNode("ArgListK")
        call_arg = TreeNode("ExpK", value="IdV v1")
        call_arg_list.children.append(call_arg)
        call_stmt.children.extend([call_proc_id, call_arg_list])
        stmlk_main.children.append(call_stmt)


        declarepart_node = TreeNode("DeclarePart", children=[typek_global, vark_global, procdeck_q])
        prok_node = TreeNode("ProK", children=[phead, declarepart_node, stmlk_main])
        return prok_node

if 'format_ast_to_display_string' not in globals():
    def format_ast_to_display_string(root_node: TreeNode | None) -> str:
        if root_node is None: return "AST is None (MOCK)"
        # 简单的AST字符串表示
        parts = []
        def _format_node_mock(node, indent_level):
            indent = "  " * indent_level
            val_str = f" (value: {node.value})" if node.value is not None else ""
            child_count = len(node.children)
            parts.append(f"{indent}{node.node_type}{val_str} [Children: {child_count}]")
            for child in node.children:
                _format_node_mock(child, indent_level + 1)
        _format_node_mock(root_node, 0)
        return "\n".join(parts)
# --- 模拟依赖结束 ---

if __name__ == "__main__":
    main_compiler_pipeline_cli()