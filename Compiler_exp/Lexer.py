import re

class Token:
    def __init__(self, type_, value):
        self.type = type_
        self.value = value
    
    def __str__(self):
        return f"({self.type}, {self.value})"

class Lexer:
    def __init__(self, source_code):
        self.source = source_code # 不再添加末尾空格，正则表达式和边界检查会处理
        self.pos = 0
        self.tokens = []
        # 保留字列表
        self.keywords = {
            "program", "type", "var", "procedure", "begin", "end",
            "if", "while", "read", "write", "then", "else", "fi",
            "endwh", "integer", "char", "array", "record", "of"
        }

        # 定义词法单元的正则表达式规则
        # (Token类型/字面量, 正则表达式字符串, [可选] 值提取函数(match_obj) -> token_value)
        # 如果值提取函数为 None，则 match.group(0) (整个匹配) 用作值。
        # Token类型/字面量将用作 Token.type，除非被覆盖（例如关键字）。
        token_specifications = [
            # 字符常量: e.g., 'a'
            #点号 . 是正则表达式中的一个元字符 (metacharacter)，具有特殊含义。
            #含义：它通常匹配除换行符 \n 之外的任意单个字符。 . 是一个通配符
            ('CHARC',       r"\'(.)\'", lambda m: m.group(1)), #用于匹配一个被单引号包围的单个字符,看到 \ 后面跟着一个通常有特殊意义的字符时，一般表示“匹配这个字符本身”。
            # 双字符分界符
            (':=' ,         r':='),        
            ('..',          r'\.\.'),      
            # 标识符 (后续会检查是否为关键字)
            ('ID',          r'[a-zA-Z][a-zA-Z0-9]*'), 
            # 无符号整数
            ('INTC',       r'(0|[1-9][0-9]*)'),    
            # 单字符分界符 - Token类型和值都是该字符本身
            ('+',           r'\+'),
            ('-',           r'-'),
            ('*',           r'\*'),
            ('/',           r'/'),
            ('<',           r'<'),
            ('=',           r'='),
            ('(',           r'\('),
            (')',           r'\)'),
            ('[',           r'\['),
            (']',           r'\]'),
            ('.',           r'\.'), # '.' 必须在 '..' 之后（通过规则顺序保证）
            (';',           r';'),
            (',',           r','),
        ]
        
        # 提取出词法单元类别、正则表达式字符串和可选的值提取函数。
        # 将字符串形式的正则表达式编译成一个更高效的正则表达式对象。
        # 将词法单元类别、编译后的正则表达式对象以及值提取函数重新组合成一个新的元组。
        # 将这个新的元组存入 self.compiled_regex_rules 列表中。
        
        self.compiled_regex_rules = []
        for cat_or_lit, pattern_str, *rest_ext in token_specifications:
            extractor_fn = rest_ext[0] if rest_ext else None
            # re.compile 编译正则表达式以提高效率
            # match() 方法将从字符串开头匹配，这正是我们所需要的
            self.compiled_regex_rules.append(
                (cat_or_lit, re.compile(pattern_str), extractor_fn)
            )

    def tokenize(self):
        while self.pos < len(self.source):
            current_char = self.source[self.pos]

            # 1. 跳过空白字符 (手动处理)
            if current_char.isspace():
                self.pos += 1
                continue
            
            # 2. 注释处理 (手动处理，以正确处理未闭合注释)
            if current_char == "{":
                start_comment_pos = self.pos
                self.pos += 1 # 跳过 '{'
                comment_closed = False
                while self.pos < len(self.source):
                    if self.source[self.pos] == "}":
                        self.pos += 1 # 跳过 '}'
                        comment_closed = True
                        break
                    self.pos += 1
                
                if not comment_closed:
                    raise Exception(f"词法错误: 未闭合的注释 从位置 {start_comment_pos} 开始")
                continue # 注释处理完毕，继续下一轮循环

            # 3. 应用正则表达式规则匹配其他词法单元
            match_found_for_current_pos = False
            substring_to_match = self.source[self.pos:]

            for token_category, regex_obj, value_extractor_fn in self.compiled_regex_rules:
                match = regex_obj.match(substring_to_match) # match() 从子字符串的开头尝试匹配
                
                if match:
                    matched_text = match.group(0) # 完整匹配的文本
                    token_value = matched_text # 默认为完整匹配文本
                    
                    if value_extractor_fn:
                        token_value = value_extractor_fn(match) # 例如，对CHARC提取group(1)

                    token_type = token_category

                    if token_category == 'ID':
                        if matched_text in self.keywords:
                            token_type = "KEYWORD" # 如果是关键字，覆盖类型
                        # token_value 保持为标识符字符串，如 "program" 或 "myVar"
                    elif token_category in ['+', '-', '*', '/', '<', '=', '(', ')', '[', ']', '.', ';', ',', ':=', '..']:
                        # 对于这些操作符/分界符，token_category 本身就是类型，
                        # matched_text (即 token_category) 也是值
                        token_type = matched_text 
                        token_value = matched_text # 例如：Token("+", "+")
                    
                    # 对于 'CHARC', 'INTC'，token_type 就是 'CHARC' 或 'INTC'
                    # token_value 已经是处理后的值 (字符或数字字符串)

                    self.tokens.append(Token(token_type, token_value))
                    self.pos += len(matched_text) # 更新位置，跳过已匹配的文本
                    match_found_for_current_pos = True
                    break # 找到了一个匹配，跳出规则循环，处理下一个字符位置
            
            if not match_found_for_current_pos:
                # 如果跳过了空白和注释后，没有正则表达式规则匹配成功
                raise Exception(f"词法错误: 未知字符 {self.source[self.pos]} 在位置 {self.pos}")
        
        self.tokens.append(Token("EOF", "EOF"))
        return self.tokens

def read_input():
    print("请输入 SNL 源程序（以空行结束输入）：")
    lines = []
    while True:
        line = input()
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)

def main():
    try:
        # 从键盘读取输入
        source_code = read_input()
        if not source_code.strip():
            print("错误: 输入为空")
            return
        
        # 创建词法分析器并生成 Token 序列
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
        
        # 输出 Token 序列
        print("\n生成的 Token 序列：")
        for token in tokens:
            print(token)
            
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    main()



# import re

# class Token:
#     def __init__(self, type_, value):
#         self.type = type_
#         self.value = value
    
#     def __str__(self):
#         return f"({self.type}, {self.value})"

# class Lexer:
#     def __init__(self, source_code):
#         self.source = source_code + " "  # 添加末尾空格避免越界
#         self.pos = 0
#         self.tokens = []
#         # 保留字列表
#         self.keywords = {
#             "program", "type", "var", "procedure", "begin", "end",
#             "if", "while", "read", "write", "then", "else", "fi",
#             "endwh", "integer", "char", "array", "record", "of"
#         }

#     def tokenize(self):
#         while self.pos < len(self.source):
#             char = self.source[self.pos]
            
#             # 跳过空白字符
#             if char.isspace():
#                 self.pos += 1
#                 continue
            
#             # 单字符分界符
#             if char in "+-*/<=()[].;,":
#                 self.tokens.append(Token(char, char))
#                 self.pos += 1
#                 continue
            
#             # 双字符分界符 :=
#             if char == ":" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "=":
#                 self.tokens.append(Token(":=", ":="))
#                 self.pos += 2
#                 continue
            
#             # 注释处理
#             if char == "{":
#                 self.pos += 1
#                 while self.pos < len(self.source) and self.source[self.pos] != "}":
#                     self.pos += 1
#                 if self.pos < len(self.source):
#                     self.pos += 1  # 跳过 }
#                 else:
#                     raise Exception("词法错误: 未闭合的注释")
#                 continue
            
#             # 数组下标界限符 ..
#             if char == "." and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == ".":
#                 self.tokens.append(Token("..", ".."))
#                 self.pos += 2
#                 continue
            
#             # 字符起始和结束符 '
#             if char == "'":
#                 if self.pos + 2 < len(self.source) and self.source[self.pos + 2] == "'":
#                     char_value = self.source[self.pos + 1]
#                 if len(char_value) == 1:  # Allow any single character
#                 # if len(char_value) == 1 and char_value.isalnum():
#                     self.tokens.append(Token("CHARC", char_value))
#                     self.pos += 3
#                     continue
#                 raise Exception(f"词法错误: 无效的字符常量 在位置 {self.pos}")
#             # 标识符或保留字
#             if char.isalpha():
#                 identifier = char
#                 self.pos += 1
#                 while self.pos < len(self.source) and (self.source[self.pos].isalnum()):
#                     identifier += self.source[self.pos]
#                     self.pos += 1
#                 token_type = "KEYWORD" if identifier in self.keywords else "ID"
#                 self.tokens.append(Token(token_type, identifier))
#                 continue
            
#             # 无符号整数
#             if char.isdigit():
#                 number = char
#                 self.pos += 1
#                 while self.pos < len(self.source) and self.source[self.pos].isdigit():
#                     number += self.source[self.pos]
#                     self.pos += 1
#                 self.tokens.append(Token("INTC", number))
#                 continue
            
#             # 错误处理
#             raise Exception(f"词法错误: 未知字符 {char} 在位置 {self.pos}")
        
#         self.tokens.append(Token("EOF", "EOF"))
#         return self.tokens

# def read_input():
#     print("请输入 SNL 源程序（以空行结束输入）：")
#     lines = []
#     while True:
#         line = input()
#         if line.strip() == "":
#             break
#         lines.append(line)
#     return "\n".join(lines)

# def main():
#     try:
#         # 从键盘读取输入
#         source_code = read_input()
#         if not source_code.strip():
#             print("错误: 输入为空")
#             return
        
#         # 创建词法分析器并生成 Token 序列
#         lexer = Lexer(source_code)
#         tokens = lexer.tokenize()
        
#         # 输出 Token 序列
#         print("\n生成的 Token 序列：")
#         for token in tokens:
#             print(token)
            
#     except Exception as e:
#         print(f"错误: {e}")

# if __name__ == "__main__":
#     main()