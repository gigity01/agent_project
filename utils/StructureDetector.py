import re


class StructureDetector:
    """
    结构识别：标题/段落/代码块/表格

    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ====================== 1. 标题识别规则（不变） ======================
    TITLE_PATTERNS = [
        re.compile(r'^#{1,6}\s+.+'),  # Markdown # 标题
        re.compile(r'^\d+\.\s+.+'),  # 1. xxx 有序列表
        re.compile(r'^第.+章.*'),  # 第1章 文档标题
        re.compile(r'^=+\s*.+\s*=+$'),  # === 标题 ===
        re.compile(r'^[一二三四五六七八九十]+、.*')  # 一、中文标题
    ]

    # ====================== 2. 代码块正则（不变） ======================
    CODE_BLOCK_PATTERN = re.compile(r'(```[\s\S]*?```)', re.MULTILINE)

    # ====================== 3. 新增：表格块正则 ======================
    # 匹配标准 Markdown 表格：表头|分隔线|内容行，完整整块提取
    TABLE_BLOCK_PATTERN = re.compile(
        r'(\|.*?\|\n\|[-:| ]+\|\n(?:\|.*?\|\n?)+)',
        re.MULTILINE
    )

    def is_title(self, line: str) -> bool:
        """判断一行是否为标题（不变）"""
        line = line.strip()
        return any(pattern.match(line) for pattern in self.TITLE_PATTERNS)

    def extract_markdown_structure(self, md_text: str) -> list:
        """
        核心：Markdown 全结构解析
        输出：[
            {"type":"section", "path":[], "content":""},
            {"type":"code", "content":""},
            {"type":"table", "content":""}
        ]
        """
        # ==========================================
        # 步骤1：【保护代码块】提取 + 占位符替换
        # ==========================================
        code_blocks = self.CODE_BLOCK_PATTERN.findall(md_text)
        temp_text = self.CODE_BLOCK_PATTERN.sub("[[CODE_BLOCK]]", md_text)

        # ==========================================
        # 步骤2：【保护表格块】提取 + 占位符替换
        # ==========================================
        table_blocks = self.TABLE_BLOCK_PATTERN.findall(temp_text)
        temp_text = self.TABLE_BLOCK_PATTERN.sub("[[TABLE_BLOCK]]", temp_text)

        # ==========================================
        # 步骤3：逐行解析剩余文本
        # ==========================================
        lines = temp_text.split("\n")
        blocks = []  # 最终结构化块列表
        current_section = []  # 当前正在收集的正文内容
        current_path = []  # 当前标题层级路径

        for line in lines:
            line = line.strip()

            # ------------------------------
            # 情况1：遇到 代码块占位符
            # ------------------------------
            if "[[CODE_BLOCK]]" in line:
                # 先保存上一段正文
                if current_section:
                    blocks.append({
                        "type": "section",
                        "path": current_path.copy(),
                        "content": "\n".join(current_section)
                    })
                    current_section = []
                # 回填真实代码块
                blocks.append({
                    "type": "code",
                    "path": current_path.copy(),
                    "content": code_blocks.pop(0)
                })

            # ------------------------------
            # 情况2：遇到 表格块占位符（新增）
            # ------------------------------
            elif "[[TABLE_BLOCK]]" in line:
                # 先保存上一段正文
                if current_section:
                    blocks.append({
                        "type": "section",
                        "path": current_path.copy(),
                        "content": "\n".join(current_section)
                    })
                    current_section = []
                # 回填真实表格块
                blocks.append({
                    "type": "table",
                    "path": current_path.copy(),
                    "content": table_blocks.pop(0)
                })

            # ------------------------------
            # 情况3：遇到 标题
            # ------------------------------
            elif self.is_title(line):
                # 保存上一段内容
                if current_section:
                    blocks.append({
                        "type": "section",
                        "path": current_path.copy(),
                        "content": "\n".join(current_section)
                    })
                    current_section = []

                # 更新标题路径
                title = line
                if title.startswith("#"):
                    level_str = title.split()[0]
                    clean_title = title.replace(level_str, "").strip()
                    current_path = [clean_title]
                else:
                    current_path = [title]

            # ------------------------------
            # 情况4：普通正文
            # ------------------------------
            else:
                if line:
                    current_section.append(line)

        # ==========================================
        # 最后：保存文本末尾剩余的内容
        # ==========================================
        if current_section:
            blocks.append({
                "type": "section",
                "path": current_path.copy(),
                "content": "\n".join(current_section)
            })

        return blocks


# 全局单例对象（不变）
detector = StructureDetector()
