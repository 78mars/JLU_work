import tkinter as tk
from tkinter import scrolledtext, font, messagebox, PanedWindow # PanedWindow用于可拖动调整的区域
from ASTparser import generate_ast_from_source, format_ast_to_display_string # 新增的函数
from analyzer import perform_semantic_analysis_from_source

from Lexer import Lexer # 从 Lexer.py 导入 Lexer 类

class PlaceholderASTNode: # 用于演示
    def __init__(self, node_type, value=None, children=None):
        self.node_type = node_type; self.value = value; self.children = children if children else []
def placeholder_format_ast(node, indent=0):
    if not node: return ""
    s = "  " * indent + f"{node.node_type}" + (f": {node.value}" if node.value else "") + "\n"
    for child in node.children: s += placeholder_format_ast(child, indent + 1)
    return s
def placeholder_format_symbol_table(table):
    if not table: return "符号表为空。"
    return "\n".join([str(entry) for entry in table])
# --- 占位符结束 ---

def run_lexical_analysis(source_code):
    """调用词法分析器并格式化Token序列。"""
    try:
        lexer_instance = Lexer(source_code)
        tokens = lexer_instance.tokenize()
        # 将Token列表转换为每行一个Token的字符串
        return "\n".join([str(token) for token in tokens])
    except Exception as e:
        # 返回格式化的错误信息
        return f"词法分析错误 (Lexical Error):\n{str(e)}"

def run_syntax_analysis(source_code):
    """调用词法和语法分析器，然后格式化AST。"""
    try:
        # 1. 调用 ASTparser.py 中的顶层函数来生成AST
        #    这个函数内部会处理词法分析和语法分析
        ast_root_node = generate_ast_from_source(source_code)
        
        # 2. 调用 ASTparser.py 中的格式化函数 (或TreeNode的__str__) 将AST转换为字符串
        #    如果 ast_root_node 为 None (虽然我们建议在出错时抛异常而不是返回None)，
        #    format_ast_to_display_string 应该能优雅处理。
        formatted_ast_string = format_ast_to_display_string(ast_root_node)
        
        return formatted_ast_string
        
    except SyntaxError as se: # 捕获由 Parser 明确抛出的语法错误
        # SyntaxError 是 Python 内置的，或者你可以定义自己的
        return f"语法分析错误 (Syntax Error):\n{str(se)}"
    # except LexicalError as le: # 如果你的词法分析器抛出自定义的 LexicalError
    #     return f"词法分析错误 (Lexical Error):\n{str(le)}"
    except Exception as e: # 捕获所有其他错误，包括词法分析器抛出的一般 Exception
        # 如果 generate_ast_from_source 内部的词法分析失败并抛出通用 Exception，
        # 这里会捕获到。
        # 最好是让词法分析器也抛出更具体的错误，例如 LexicalError。
        return f"分析过程中发生错误 (Error during analysis):\n{str(e)}"


def run_semantic_analysis_in_gui(source_code):
    if not source_code.strip():
        return "请输入源代码。", "", "AST未生成。", ["错误: 源代码为空。"] # 返回四个值

    # 调用 analyzer.py 中的顶层函数
    # 它返回 (符号表字符串, 错误字符串, AST字符串, 完整日志列表)
    symbol_table_str, combined_error_str, ast_str, full_listing_for_file = \
        perform_semantic_analysis_from_source(source_code, trace_to_console_for_debug=False) # GUI通常不需要控制台跟踪
    
    # 1. 将 full_listing_for_file 保存到 listing.txt
    try:
        with open("listing.txt", "w", encoding="utf-8") as f:
            if full_listing_for_file:
                for line in full_listing_for_file:
                    f.write(line + "\n")
            else: # 备用，如果日志列表意外为空
                f.write("分析未能生成详细日志。\n")
                if combined_error_str and combined_error_str != "无错误报告。":
                    f.write("\n捕获到的错误:\n")
                    f.write(combined_error_str)
        # (可选) 提示保存成功
    except IOError as e:
        messagebox.showerror("保存错误", f"无法写入 listing.txt: {e}")

    # 2. 准备在GUI中显示的内容
    # GUI的输出区域现在可以直接显示 full_listing_for_file 的内容，
    # 因为它应该已经包含了所有信息（包括错误、符号表快照等）。
    # 或者，你仍然可以像之前一样，优先显示格式化的符号表和错误字符串，
    # 而 full_listing_for_file 主要用于写入文件。
    # 这里我们选择显示 full_listing_for_file，因为它更全面。
    
    if full_listing_for_file:
        gui_output_string = "\n".join(full_listing_for_file)
    else: # 如果日志列表为空的备用显示
        gui_output_string = f"--- AST ---\n{ast_str}\n\n"
        gui_output_string += f"--- 符号表 ---\n{symbol_table_str}\n\n"
        if combined_error_str and combined_error_str != "无错误报告。":
            gui_output_string += f"--- 错误信息 ---\n{combined_error_str}"
        else:
            gui_output_string += "--- 分析完成 (可能无详细日志输出) ---"
            
    return gui_output_string # 或者返回元组让GUI的调用者决定如何组合显示

class CompilerGUI:
    def __init__(self, master_window):
        self.master = master_window
        master_window.title("SNL 编译器图形界面")
        master_window.geometry("1200x750") # 调整窗口大小

        # 定义一些字体
        self.text_area_font = font.Font(family="Consolas", size=11) # 等宽字体适合代码
        self.label_font = font.Font(family="Arial", size=10, weight="bold")
        self.button_font = font.Font(family="Arial", size=10)

        # 使用PanedWindow来创建可拖动调整左右区域的布局
        self.main_pane = PanedWindow(master_window, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- 左侧区域: 源代码输入 ---
        left_panel_frame = tk.Frame(self.main_pane, bd=2, relief=tk.GROOVE) # 加个边框
        tk.Label(left_panel_frame, text="SNL 源代码输入:", font=self.label_font).pack(pady=(5,2), anchor="w", padx=5)
        self.source_input_text = scrolledtext.ScrolledText(left_panel_frame, wrap=tk.WORD, undo=True,
                                                           font=self.text_area_font, height=20, width=60)
        self.source_input_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        self.main_pane.add(left_panel_frame, stretch="always", minsize=350) # minsize防止区域过小

        # --- 右侧容器: 包含输出区域和按钮区域 ---
        right_container_frame = tk.Frame(self.main_pane)
        self.main_pane.add(right_container_frame, stretch="always", minsize=450)

        # --- 右侧区域 (上部): 分析结果输出 ---
        tk.Label(right_container_frame, text="分析结果:", font=self.label_font).pack(pady=(5,2), anchor="w", padx=5)
        self.analysis_output_text = scrolledtext.ScrolledText(right_container_frame, wrap=tk.WORD, state=tk.DISABLED, # 初始为只读
                                                              font=self.text_area_font, height=18, width=70)
        self.analysis_output_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,10))

        # --- 右侧区域 (下部): 控制按钮 ---
        controls_frame = tk.Frame(right_container_frame, pady=5)
        controls_frame.pack(fill=tk.X, side=tk.BOTTOM)

        lex_button = tk.Button(controls_frame, text="词法分析", command=self.trigger_lexical_analysis, font=self.button_font, width=12)
        lex_button.pack(side=tk.LEFT, padx=10, pady=5)

        syntax_button = tk.Button(controls_frame, text="语法分析", command=self.trigger_syntax_analysis, font=self.button_font, width=12)
        syntax_button.pack(side=tk.LEFT, padx=10, pady=5)

        semantic_button = tk.Button(controls_frame, text="语义分析", command=self.trigger_semantic_analysis, font=self.button_font, width=12)
        semantic_button.pack(side=tk.LEFT, padx=10, pady=5)
        
        clear_input_button = tk.Button(controls_frame, text="清空输入", command=self.clear_source_input, font=self.button_font, width=10)
        clear_input_button.pack(side=tk.RIGHT, padx=(20,5), pady=5) # 放右边，加点左边距

        clear_output_button = tk.Button(controls_frame, text="清空输出", command=self.clear_analysis_output, font=self.button_font, width=10)
        clear_output_button.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # 初始化PanedWindow的分割条位置 (例如，大约40%给左边)
        master_window.update_idletasks() # 确保组件已绘制，以便获取窗口宽度
        initial_sash_position = int(master_window.winfo_width() * 0.4)
        if initial_sash_position > 50 : # 避免初始位置太小
             self.main_pane.sash_place(0, initial_sash_position, 0)


    def _display_output(self, content_string):
        """辅助函数，用于在输出区域显示内容。"""
        self.analysis_output_text.config(state=tk.NORMAL) # 先设为可编辑
        self.analysis_output_text.delete(1.0, tk.END)     # 清空旧内容
        self.analysis_output_text.insert(tk.END, content_string) # 插入新内容
        self.analysis_output_text.config(state=tk.DISABLED) # 再设为只读

    def _get_source_code_from_input(self):
        """从输入框获取源代码，如果为空则提示。"""
        source = self.source_input_text.get(1.0, tk.END).strip()
        if not source:
            messagebox.showwarning("输入为空", "请输入SNL源代码后再进行分析。")
            return None
        return source

    def trigger_lexical_analysis(self):
        source_code = self._get_source_code_from_input()
        if source_code is not None:
            result_string = run_lexical_analysis(source_code)
            self._display_output(result_string)

    def trigger_syntax_analysis(self):
        source_code = self._get_source_code_from_input()
        if source_code is not None:
            result_string = run_syntax_analysis(source_code)
            self._display_output(result_string)

    def trigger_semantic_analysis(self):
        source_code = self._get_source_code_from_input()
        if source_code is not None:
            result_string = run_semantic_analysis_in_gui(source_code)
            self._display_output(result_string)
            
    def clear_source_input(self):
        self.source_input_text.delete(1.0, tk.END)

    def clear_analysis_output(self):
        self._display_output("")


if __name__ == "__main__":
    main_window = tk.Tk()
    gui_app = CompilerGUI(main_window)
    main_window.mainloop()