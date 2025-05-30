from Lexer import Lexer, Token 

class TreeNode:
    def __init__(self, node_type, value=None):
        self.node_type = node_type # AST 节点类型, e.g., "PheadK", "AssignK"
        self.value = value       # 节点关联的值, e.g., program name, operator, var name, const value
        self.children = []

    def add_child(self, child):
        if child is not None: # 确保不添加None子节点
            self.children.append(child)

    def __str__(self, level=0):
        indent = "  " * level # 使用两个空格作为缩进单位
        node_str = f"{indent}{self.node_type}"
        if self.value is not None: # 检查 value 是否为 None
            node_str += f" {self.value}" # 书上的风格通常是类型和值在一行
        
        for child in self.children:
            node_str += "\n" + child.__str__(level + 1)
        return node_str

class Parser: # 这个类名应该与你在 analyzer.py 中导入时使用的名称一致 (AS ASTParser)
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.current_token = self.tokens[self.pos] if self.pos < len(self.tokens) else Token("EOF", "EOF")
        self.root = None

    def advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]
        else:
            self.current_token = Token("EOF", "EOF")

    def match(self, expected_type, expected_value=None):
        token = self.current_token
        if token.type == expected_type:
            if expected_value is None or token.value == expected_value:
                self.advance()
                return token
            else:
                raise Exception(f"语法错误: 期待值 {expected_value} for {expected_type}, 实际 {token.value} at pos {self.pos}")
        else:
            raise Exception(f"语法错误: 期待类型 {expected_type}, 实际 {token.type} ({token.value}) at pos {self.pos}")

    def program(self):
        # 1. node = TreeNode("ProK")
        #    首先，创建一个 TreeNode 对象，作为整个程序抽象语法树 (AST) 的根节点
        node = TreeNode("ProK") 
        #接着，调用 self.program_head() 方法去解析程序的头部。
        node.add_child(self.program_head())
        #    检查当前的词法单元 (token) 是否是关键字 "type"。
    #    如果是，说明接下来是类型声明部分。
    #    于是调用 self.type_declarations() 方法去解析所有的类型声明。
        if self.current_token.type == "KEYWORD" and self.current_token.value == "type":
            node.add_child(self.type_declarations())
#    类似地，检查当前的词法单元是否是关键字 "var"。
    #    如果是，说明接下来是变量声明部分。
    #    调用 self.var_declarations() 方法去解析所有的变量声明。
        if self.current_token.type == "KEYWORD" and self.current_token.value == "var":
            node.add_child(self.var_declarations())
#    只要当前的词法单元是关键字 "procedure"，就认为还有一个过程声明需要解析。
    #    调用 self.proc_declaration() 方法解析一个过程声明。
        while self.current_token.type == "KEYWORD" and self.current_token.value == "procedure":
            node.add_child(self.proc_declaration()) 

        node.add_child(self.program_body())
        self.match(".") 
        return node

    def program_head(self):
        self.match("KEYWORD", "program") 
        id_token = self.match("ID")
        return TreeNode("PheadK", value=id_token.value)

    def type_declarations(self):
        node = TreeNode("TypeK")
        self.match("KEYWORD", "type") 
        while self.current_token.type == "ID": 
            type_id_token = self.match("ID")
            self.match("=") 
            type_name_node = self.type_name() 
            self.match(";") 
            
            dec_node = TreeNode("DecK", value=type_id_token.value) 
            dec_node.add_child(type_name_node) 
            node.add_child(dec_node)
        return node

    def type_name(self):
        token = self.current_token
        if token.type == "KEYWORD":
            if token.value == "integer":
                self.advance()
                return TreeNode("IntegerK")
            elif token.value == "char":
                self.advance()
                return TreeNode("CharK")
            # TODO: elif token.value == "array": return self.array_type_ast_node_creation()
            # TODO: elif token.value == "record": return self.record_type_ast_node_creation()
            else: 
                raise Exception(f"Unexpected keyword for type: {token.value}")
        elif token.type == "ID": 
            self.advance()
            return TreeNode("IdK", value=token.value) 
        else:
            raise Exception(f"Invalid token for type name: {token}")

    def var_declarations(self):
        node = TreeNode("VarK")
        self.match("KEYWORD", "var") 
        
        while (self.current_token.type == "ID") or \
              (self.current_token.type == "KEYWORD" and \
               self.current_token.value in ["integer", "char"]): # 简化：目前只支持integer, char和用户定义类型ID
                                                                  # 如果支持 array, record, 在此添加
            
            type_ast_node = self.type_name() 
            
            var_names_nodes = []
            id_token = self.match("ID")
            var_names_nodes.append(TreeNode("IdK", value=id_token.value)) 
            
            while self.current_token.type == ",":
                self.match(",") 
                id_token = self.match("ID")
                var_names_nodes.append(TreeNode("IdK", value=id_token.value))
            
            self.match(";") 
            
            dec_node = TreeNode("DecK") 
            dec_node.add_child(type_ast_node) 
            for var_node in var_names_nodes:
                dec_node.add_child(var_node)
            node.add_child(dec_node)
        return node

    def proc_declaration(self):
        self.match("KEYWORD", "procedure")
        proc_name_token = self.match("ID")
        proc_node = TreeNode("ProcDecK", value=proc_name_token.value)

        self.match("(")
        if self.current_token.type != ")": 
            param_dec_list_node = self.param_dec_list() 
            proc_node.add_child(param_dec_list_node) 
        self.match(")")
        self.match(";")

        if self.current_token.type == "KEYWORD" and self.current_token.value == "type":
            proc_node.add_child(self.type_declarations())

        if self.current_token.type == "KEYWORD" and self.current_token.value == "var":
            proc_node.add_child(self.var_declarations())

        proc_node.add_child(self.program_body()) 
        return proc_node

    def param_dec_list(self):
        param_list_node = TreeNode("ParamListK") 
        while True: 
            param_mode = "value" 
            if self.current_token.type == "KEYWORD" and self.current_token.value == "var":
                self.match("KEYWORD", "var")
                param_mode = "var" 
            
            type_ast_node = self.type_name() 
            
            param_names_nodes = []
            id_token = self.match("ID")
            param_names_nodes.append(TreeNode("IdK", value=id_token.value))
            
            while self.current_token.type == ",":
                self.match(",")
                id_token = self.match("ID")
                param_names_nodes.append(TreeNode("IdK", value=id_token.value))

            dec_node = TreeNode("DecK", value=f"{param_mode} param") 
            dec_node.add_child(type_ast_node)
            for name_node in param_names_nodes:
                dec_node.add_child(name_node)
            param_list_node.add_child(dec_node)

            if self.current_token.type == ";":
                self.match(";") 
                if self.current_token.type == ")": 
                    break 
            else: 
                break
        return param_list_node

    def program_body(self):
        #    函数首先期望并匹配关键字 "begin"。
        self.match("KEYWORD", "begin")
        #代表 "Statement List Kind"
        stm_list_node = TreeNode("StmLK")
        
        if not (self.current_token.type == "KEYWORD" and self.current_token.value == "end"):
            stm_node = self.stm()
            stm_list_node.add_child(stm_node)
        
            while self.current_token.type == ";":
                self.match(";") 
                if self.current_token.type == "KEYWORD" and self.current_token.value == "end":
                    break 
                if self.current_token.type == "EOF": 
                    raise Exception("Unexpected EOF in statement list")
                stm_node = self.stm()
                stm_list_node.add_child(stm_node)
        
        self.match("KEYWORD", "end")
        return stm_list_node

    def stm(self):
        token = self.current_token# 获取当前的词法单元，用于做决策
        # 情况一：语句以关键字 (KEYWORD) 开头
        if token.type == "KEYWORD":
            # 如果关键字是 "if"，那么这是一条条件语句。
            # 将解析任务委托给 self.conditional_stm() 函数
            if token.value == "if":
                return self.conditional_stm()
            elif token.value == "read":
                return self.input_stm() # 调用修正后的 input_stm
            elif token.value == "write":
                return self.output_stm()
            else:
                raise Exception(f"Unexpected keyword statement: {token.value}")
        elif token.type == "ID":
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos+1].type == "(":
                proc_id_token = self.match("ID")
                call_node = TreeNode("StmtK", value="Call") 
                call_node.add_child(TreeNode("ProcIdK", value=proc_id_token.value)) 
                
                self.match("(")
                arg_list_node = TreeNode("ArgListK") 
                if self.current_token.type != ")":
                    arg_list_node.add_child(self.exp()) 
                    while self.current_token.type == ",":
                        self.match(",")
                        arg_list_node.add_child(self.exp())
                self.match(")")
                if arg_list_node.children: 
                    call_node.add_child(arg_list_node)
                return call_node
            else: 
                assign_node = TreeNode("StmtK", value="Assign")
                lhs_var_node = self.variable() 
                assign_node.add_child(lhs_var_node)
                self.match(":=") 
                rhs_exp_node = self.exp()
                assign_node.add_child(rhs_exp_node)
                return assign_node
        else:
            raise Exception(f"Invalid start of statement: {token}")

    def conditional_stm(self):
        self.match("KEYWORD", "if")
        if_node = TreeNode("StmtK", value="If")
        condition_exp_node = self.exp() 
        if_node.add_child(condition_exp_node)
        self.match("KEYWORD", "then")
        if_node.add_child(self.stm_list_for_control_flow()) # 使用独立的语句列表解析
        if self.current_token.type == "KEYWORD" and self.current_token.value == "else":
            self.match("KEYWORD", "else")
            if_node.add_child(self.stm_list_for_control_flow()) # 使用独立的语句列表解析
        else: 
              if_node.add_child(TreeNode("StmLK")) 
        self.match("KEYWORD", "fi")
        return if_node
        
    def stm_list_for_control_flow(self):
        list_node = TreeNode("StmLK")
        # SNL的if/while子句中的StmList至少有一个Stm
        if self.current_token.type not in ["KEYWORD"] or \
           self.current_token.value not in ["else", "fi", "endwh", "end"]: # 确保不是直接结束
            list_node.add_child(self.stm())
            while self.current_token.type == ";":
                self.match(";")
                if self.current_token.type == "KEYWORD" and \
                   self.current_token.value in ["else", "fi", "endwh", "end"]:
                    break
                list_node.add_child(self.stm())
        return list_node

    # input_stm 方法中的修改点，确保子节点是正确的类型
    def input_stm(self):
        self.match("KEYWORD", "read")
        read_node = TreeNode("StmtK", value="Read")
        self.match("(")
        id_token = self.match("ID")
        # 根据你的AST设计，read的子节点应该是变量本身，而不是ExpK。
        # 如果你的语义分析器期望read(x)的x是一个变量节点，那么这里应该是：
        # variable_node = TreeNode("IdK", value=id_token.value) # 或者更复杂的 self.variable() 如果read支持复杂变量
        # read_node.add_child(variable_node)
        # 如果你的设计确实是 ExpK IdV，那么你原来的也没错，但要确保一致性。
        # 我们暂时保留你原来的，但请注意这里的AST结构对后续分析很重要。
        variable_expression_node = TreeNode("ExpK", value=f"IdV {id_token.value}")
        read_node.add_child(variable_expression_node)
        self.match(")")
        return read_node


    def output_stm(self):
        self.match("KEYWORD", "write")
        write_node = TreeNode("StmtK", value="Write")
        self.match("(")
        exp_node = self.exp() 
        write_node.add_child(exp_node)
        self.match(")")
        return write_node

    def exp(self):
        node = self.simple_exp()
        if self.current_token.type in ["<", "="]: # 仅处理 < 和 = 作为关系运算符
            op_token = self.current_token # self.match(self.current_token.type) 会消耗
            self.advance() 
            right_node = self.simple_exp()
            op_node = TreeNode("ExpK", value=f"Op {op_token.value}") 
            op_node.add_child(node) 
            op_node.add_child(right_node) 
            return op_node
        else:
            return node 

    def simple_exp(self): 
        node = self.term()
        while self.current_token.type in ["+", "-"]:
            op_token = self.current_token
            self.advance()
            right_node = self.term()
            op_node = TreeNode("ExpK", value=f"Op {op_token.value}")
            op_node.add_child(node)
            op_node.add_child(right_node)
            node = op_node 
        return node

    def term(self): 
        node = self.factor()
        while self.current_token.type in ["*", "/"]: # 假设词法分析器能区分 / 和注释
            op_token = self.current_token
            self.advance()
            right_node = self.factor()
            op_node = TreeNode("ExpK", value=f"Op {op_token.value}")
            op_node.add_child(node)
            op_node.add_child(right_node)
            node = op_node 
        return node

    def factor(self):
        token = self.current_token
        if token.type == "INTC":
            self.advance()
            return TreeNode("ExpK", value=f"Const {token.value}") # token.value 已是整数
        elif token.type == "ID":
            return self.variable() 
        elif token.type == "(":
            self.match("(")
            exp_node = self.exp() 
            self.match(")")
            return exp_node 
        else:
            raise Exception(f"Invalid factor: {token.type} ({token.value})")

    def variable(self):
        id_token = self.match("ID")
        var_node = TreeNode("ExpK", value=f"IdV {id_token.value}") 

        # 检查数组访问
        if self.current_token.type == "[": 
            self.match("[")
            index_exp = self.exp() # 数组下标是表达式
            self.match("]")
            
            access_node = TreeNode("ExpK", value="ArrayAccess") 
            access_node.add_child(var_node) # 数组基变量 (已经是 ExpK IdV ...)
            access_node.add_child(index_exp) # 索引表达式
            return access_node 
        
        # TODO: 可以在这里添加对记录域访问 . 的处理
        # elif self.current_token.type == ".":
        #     self.match(".")
        #     field_id_token = self.match("ID")
        #     access_node = TreeNode("ExpK", value="FieldAccess")
        #     access_node.add_child(var_node) # 记录基变量
        #     # 域名通常不作为完整表达式处理，而是直接作为标识符
        #     access_node.add_child(TreeNode("FieldIdK", value=field_id_token.value)) 
        #     return access_node
            
        return var_node 

    def parse(self):
        """
        执行语法分析并返回AST的根节点。
        如果发生错误，则抛出异常。
        """
        try:
            # program() 方法是你的起始产生式，它应该返回整个程序的AST根节点
            ast_root_node = self.program()

            if self.current_token.type != "EOF":
                # 如果所有Token没有被完全消耗 (除了最后的EOF)
                raise SyntaxError(f"语法错误: 输入未完全解析，在 '{self.current_token}' 处停止。")
            
            # 如果成功，返回AST的根
            return ast_root_node
        except SyntaxError as se: # 捕获在match或其他地方抛出的SyntaxError
            # print(f"语法分析失败: {se}") # GUI会处理错误的显示，这里可以不用打印
            raise # 将异常重新抛出，以便上层(GUI)捕获和处理
        except Exception as e: # 捕获其他可能的意外错误
            # print(f"语法分析过程中发生意外错误: {e}")
            # print(f"错误发生在词法单元索引 {self.pos} 附近, 当前词法单元: {self.current_token}")
            raise SyntaxError(f"语法分析意外中断: {e} (在词法单元索引 {self.pos} 附近, 当前词法单元: {self.current_token})") # 包装成SyntaxError

# --- 主函数部分（用于测试，如果需要） ---
def read_input_for_parser(): # 与 analyzer.py 中的 read_snl_input 区分
    print("请输入 SNL 源程序 (用于 ASTParser 测试，连续两个空行结束):")
    lines = []
    empty_line_consecutive_count = 0
    while True:
        try:
            line = input()
            if not line.strip():
                empty_line_consecutive_count += 1
                if empty_line_consecutive_count >= 2 and lines: 
                    if lines and not lines[-1].strip(): lines.pop()
                    break
                elif not lines and empty_line_consecutive_count >=1 : 
                    break 
            else: 
                empty_line_consecutive_count = 0 
            lines.append(line)
        except EOFError: 
            break
    return "\n".join(lines)


# --- 用于GUI调用的顶层函数 ---
def generate_ast_from_source(source_code_string):
    """
    接收源代码字符串，执行词法分析和语法分析，返回AST根节点。
    如果发生错误，此函数会从 Lexer 或 Parser 传播异常。
    """
    # 1. 词法分析
    lexer = Lexer(source_code_string) # Lexer的构造函数应接收源代码字符串
    tokens = lexer.tokenize()         # tokenize() 应返回Token列表或抛出词法错误

    # 2. 语法分析
    # (可选) 检查tokens是否为空或只有EOF，避免不必要的解析器实例化
    if not tokens or (len(tokens) == 1 and tokens[0].type == "EOF"):
        # 可以返回一个表示空程序的特殊节点，或抛出错误，或让Parser处理
        # return TreeNode("EmptyProgramK") # 例如
        pass # Parser的 __init__ 应该能处理空token列表的情况（通过检查长度）

    parser_instance = Parser(tokens)    # Parser的构造函数应接收Token列表
    ast_root = parser_instance.parse()  # parse() 应返回AST根节点或抛出语法错误
    
    return ast_root

# --- AST 格式化函数 (从 TreeNode 的 __str__ 方法独立出来，更灵活) ---
def format_ast_to_display_string(ast_node_root):
    """
    将AST根节点转换为格式化的字符串，用于GUI显示。
    实际上是调用 TreeNode 的 __str__ 方法。
    """
    if ast_node_root is None:
        return "AST未能生成 (根节点为 None)。"
    return str(ast_node_root) # TreeNode.__str__ 会完成实际的格式化工作

# --- 主函数部分（用于单独测试 ASTParser.py） ---
# read_input_for_parser() 保持不变

if __name__ == "__main__":
    try:
        source_code = read_input_for_parser() # 使用你原来的输入函数
        if not source_code.strip():
            print("错误: 输入为空")
        else:
            print("\n--- 开始词法分析 ---")
            lexer_test = Lexer(source_code)
            tokens_test = lexer_test.tokenize()
            print("词法分析结果:")
            for t in tokens_test: print(t)
            print("--- 词法分析结束 ---\n")

            if tokens_test and not (len(tokens_test) == 1 and tokens_test[0].type == "EOF"):
                print("--- 开始语法分析 ---")
                # 直接使用顶层函数进行测试
                ast_tree_root = generate_ast_from_source(source_code) # 使用新的顶层函数
                
                if ast_tree_root:
                    print("语法分析成功！")
                    print("抽象语法树 (AST)：")
                    # 使用独立的格式化函数来获取字符串
                    formatted_ast_string = format_ast_to_display_string(ast_tree_root)
                    print(formatted_ast_string)
                else:
                    # generate_ast_from_source 在错误时应该抛出异常，所以这里理论上不会执行
                    print("AST 解析返回 None (可能在 generate_ast_from_source 中被捕获并返回了 None，应改为抛出异常)")
                print("--- 语法分析结束 ---")
            else:
                print("词法分析未产生足够Token进行语法解析。")

    except Exception as e: # 捕获来自 Lexer 或 Parser 的异常
        print(f"\nASTParser 测试主程序中捕获到错误:\n{e}")
        # import traceback # 如果需要详细堆栈跟踪
        # traceback.print_exc()