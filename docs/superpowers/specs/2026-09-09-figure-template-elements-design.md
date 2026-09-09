# 图库模板「可画元素」声明与题图一致性约束

日期：2026-09-09
状态：已批准设计，待实现

## 背景

生题时出现题干提及连线 AC₁，但所选图库模板 `cuboid-aux-2019-national-ii-17` 的 template 体只写死了 BE、EC1 两条辅助线，`showaux` 只是总开关，既没有 AC₁，也没有参数能开启 AC₁。结果题干与配图不一致。

根因有三：

1. **模板缺地面真相**：模板没有一份结构化的"本模板能画哪些点/线"清单，模型无从判断题干里的 AC₁ 到底画不画得出来。
2. **目录提示词只传 desc/params/whenNotToUse**：desc 是自由文本，且该模板 desc 写了"绘制 BE、EC1 **等**空间辅助线"——"等"字误导模型以为还能画别的连线。
3. **生题系统提示词 rule10 只有单向约束**：只说了"图里会显示的标签必须在题干定义"，没说反向"题干提到的连线必须能被模板画出来"。

## 目标

让模型在命题时拥有"模板能画什么"的地面真相，并用双向提示词约束保证题干与图形点/线一致。方向已定为**约束题干贴合模板**：题干只能引用模板能力清单内的点/线，清单外的连线不得在题干中作为配图需要显示的元素出现。

## 非目标

- 不改渲染链路（`renderFigureRefs` / `TikzCompiler`）。
- 不加渲染后实体抽取一致性校验（方案3，留作后续可选项）。
- 不改前端。
- 不一次性回填全部模板的 elements（字段可选，按需补）。

## 设计

### 1. 数据模型：`FigureTemplate` 新增 `elements` 字段

`seeview/src/main/java/com/yuanxuan/seeview/dto/FigureTemplate.java`：

- 主 record 末尾新增字段：

```java
/** 本模板能显示的图形元素清单（顶点/棱上点/辅助线/角等），供模型判断题干与图一致性；可选，缺省视为不校验 */
List<String> elements
```

- 内部 `Catalog` record 同步加同名字段 `List<String> elements`（目录提示词注入需要）。

约定：

- 可选字段：旧模板没有也能加载（Jackson 反序列化缺省为 null → 视为"该模板未声明能力，不做一致性约束"），避免一次性回填全部模板。
- 元素写法：点用字母（`A`、`B1`、`E`），线段用两端字母拼接（`BE`、`EC1`、`AC1`），与题干里 `$AC_1$` 这类写法对应——提示词里会说明"下标平铺，AC1 即 AC₁"。

### 2. Service 透传

`seeview/src/main/java/com/yuanxuan/seeview/service/FigureLibraryService.java` 的 `list()` 方法里，`new FigureTemplate.Catalog(...)` 调用追加 `t.elements()`。

### 3. 目录提示词透传 elements

`LangChainController.figureCatalogPrompt()`：每个模板条目末尾，仅当 `elements != null && !isEmpty()` 时追加一行：

```
   可画元素：A, B, C, D, A1, B1, C1, D1, E, BE, EC1
```

没声明的模板不输出该行（不改变旧行为）。

### 4. 生题系统提示词 rule10 加反向约束

`LangChainController.questionSystemPrompt()` 的 rule10（指定/未指定两份都要加），在现有"图里有→题干必须有"之后追加反向约束句：

> 反向同样要求：题干中提及的每一个图形点、连线、辅助线，必须落在所选模板「可画元素」清单内；清单未列出的点/线不得在题干中作为配图需要显示的元素出现（可作为纯文字推理过程的中间量，但不得要求配图显示）。若题干所需连线模板画不出，应改用能覆盖该连线的模板，或对该题放弃 fig 引用改用 ```tikz 自由绘制。

### 5. 回填范围

先回填出问题的立体几何这批，重点 `cuboid-aux-2019-national-ii-17`：

- `elements`: `["A","B","C","D","A1","B1","C1","D1","E","BE","EC1"]`——**不列 AC1**，从根上阻止题干再要 AC1。
- 修正该模板 `desc` 的"等"字误导，改为"仅绘制 BE、EC1 两条辅助线"。

其余模板按需后续补，字段可选故不影响运行。

### 6. 测试

- **Java**：`FigureLibraryServiceTest`
  - 加载含 elements 的模板，断言 `list()` 透传到 Catalog、`figureCatalogPrompt` 输出含"可画元素"行。
  - 加载无 elements 的旧模板不报错、不输出该行。
- **提示词**：`LangChainControllerTest`（反射惯例）断言 rule10 文本含反向约束句。
- **模板回填**：人工核对 cuboid 模板 elements 与实际 template 画的线一致（BE、EC1 有，AC1 无）。

## 改动面清单

| 文件 | 改动 |
|---|---|
| `FigureTemplate.java` | 主 record + Catalog record 各加 `elements` 字段 |
| `FigureLibraryService.java` | `list()` 透传 `t.elements()` |
| `LangChainController.java` | `figureCatalogPrompt()` 输出可画元素行；`questionSystemPrompt()` rule10 两份各加反向约束 |
| `figure_library/figures/solid_geometry/cuboid-aux-2019-national-ii-17.json` | 加 `elements`，修正 desc "等"字 |
| `FigureLibraryServiceTest.java` / `LangChainControllerTest.java` | 对应测试 |

不碰渲染链路、不碰前端。
