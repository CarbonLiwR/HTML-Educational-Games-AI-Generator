import React, {useState} from "react";
import {Modal, Input, Button, message} from "antd";
import {CaretRightOutlined, SaveOutlined, CloseOutlined} from "@ant-design/icons";

const AddGameModal = ({visible, onClose, onSave, askName, askRules}) => {
    const [gameName, setGameName] = useState("");
    const [gameRules, setGameRules] = useState("");
    const [htmlCode, setHtmlCode] = useState("");
    const [loadingName, setLoadingName] = useState(false); // 控制生成名称按钮的加载状态
    const [loadingRules, setLoadingRules] = useState(false); // 控制生成规则按钮的加载状态
    const isValidHtml = (code) => {
            const trimmedCode = code.trim();
            // 检查是否包含常见的 HTML 标签
            const hasHtmlTags = /<\/?[a-z][\s\S]*>/i.test(trimmedCode);
            // 检查是否至少包含 <html> 或 <body> 或其他结构性标签
            const containsStructuralTags = /<html|<body|<div|<span|<p|<h[1-6]|<table|<ul|<ol|<li|<img|<form/i.test(trimmedCode);
            // 如果包含 HTML 标签并且至少有结构性标签，则认为是有效 HTML
            return hasHtmlTags && containsStructuralTags;
        };

    const handleGenerateName = async () => {
        if (!htmlCode) {
            message.error("请先填写 HTML 代码内容！");
            return;
        }

        if (!isValidHtml(htmlCode)) {
            message.error("请输入有效的 HTML 代码！");
            return;
        }

        setLoadingName(true); // 开启加载状态
        try {
            const name = await askName(htmlCode); // 调用后端接口获取游戏名称
            const cleanName = name.replace(/^"(.*)"$/, "$1");
            setGameName(cleanName); // 设置生成的游戏名称
            message.success("AI 已生成游戏名称！");
        } catch (error) {
            message.error("生成游戏名称失败，请稍后重试！");
        } finally {
            setLoadingName(false); // 关闭加载状态
        }
    };

    const handleGenerateRules = async () => {
        if (!htmlCode) {
            message.error("请先填写 HTML 代码内容！");
            return;
        }

        if (!isValidHtml(htmlCode)) {
            message.error("请输入有效的 HTML 代码！");
            return;
        }

        setLoadingRules(true); // 开启加载状态
        try {
            const rules = await askRules(htmlCode); // 调用后端接口获取游戏规则
            const cleanRules = rules.replace(/^"(.*)"$/, "$1").replace(/\\n/g, " ");
            setGameRules(cleanRules); // 设置生成的游戏规则
            message.success("AI 已生成游戏规则！");
        } catch (error) {
            message.error("生成游戏规则失败，请稍后重试！");
        } finally {
            setLoadingRules(false); // 关闭加载状态
        }
    };

    const runHtmlCode = (code) => {
        // 打开新窗口
        const newWindow = window.open("", "_blank", "width=1000,height=800");

        if (newWindow) {
            // 将HTML代码写入新窗口
            newWindow.document.open();
            newWindow.document.write(code);
            newWindow.document.close();
        } else {
            alert("弹出窗口被阻止，请允许弹出窗口后重试");
        }
    };

    const clearAll=()=>{
        setGameName("");
        setGameRules("");
        setHtmlCode("");
    }

    const handleSave = () => {
        if (!gameName || !gameRules || !htmlCode) {
            message.error("请填写完整的游戏信息！");
            return;
        }

        const gameUuid = Math.random().toString(36).substring(2, 10).toUpperCase();
        onSave({name: gameName, rules: gameRules, code: htmlCode, uuid:gameUuid ,url: ""});
        message.success("游戏已保存！");
        clearAll();
        onClose();
    };

    return (
        <Modal
            title="添加游戏"
            visible={visible}
            onCancel={onClose}
            footer={null}
            width="60%"
            style={{top: 20}}
        >
            <div
                style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                }}
            >
                {/* 游戏名称输入框 */}
                <div style={{display: "flex", alignItems: "center", gap: "10px"}}>
                    <Input
                        value={gameName}
                        onChange={(e) => setGameName(e.target.value)}
                        placeholder="请输入游戏名称"
                        style={{flex: 1}}
                    />
                    <Button
                        onClick={handleGenerateName}
                        loading={loadingName} // 按钮加载状态
                    >
                        {loadingName ? "生成中..." : "AI生成"}
                    </Button>
                </div>

                {/* 游戏规则输入框 */}
                <div style={{display: "flex", alignItems: "center", gap: "10px"}}>
                    <Input.TextArea
                        value={gameRules}
                        onChange={(e) => setGameRules(e.target.value)}
                        placeholder="请输入游戏规则"
                        rows={1}
                        style={{flex: 1}}
                    />
                    <Button
                        onClick={handleGenerateRules}
                        loading={loadingRules} // 按钮加载状态
                    >
                        {loadingRules ? "生成中..." : "AI生成"}
                    </Button>
                </div>

                {/* 游戏 HTML 代码输入框 */}
                <div>
                    <Input.TextArea
                        value={htmlCode}
                        onChange={(e) => setHtmlCode(e.target.value)}
                        placeholder="请输入游戏 HTML 代码"
                        rows={8}
                        style={{marginBottom: "10px"}}
                    />
                    <div style={{display: "flex", justifyContent: "space-between", marginTop: "10px"}}>
                        <Button
                            type="primary"
                            icon={<CaretRightOutlined/>}
                            onClick={() => runHtmlCode(htmlCode)}
                            style={{marginRight: "auto"}} // 左对齐
                        >
                            调试运行
                        </Button>
                        <Button
                            type="default"
                            icon={<CloseOutlined/>}
                            onClick={clearAll} // 调用清空函数
                            style={{marginLeft: "auto"}} // 右对齐
                        >
                            清空
                        </Button>
                    </div>
                </div>

                {/* 底部保存和取消按钮 */}
                <div
                    style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        gap: "10px",
                        marginTop: "16px",
                    }}
                >
                    {/*<Button*/}
                    {/*    icon={<CloseOutlined/>}*/}
                    {/*    onClick={onClose}*/}
                    {/*    style={{backgroundColor: "#f5f5f5", borderColor: "#d9d9d9"}}*/}
                    {/*>*/}
                    {/*取消*/}
                    {/*</Button>*/}
                    <Button
                        type="primary"
                        icon={<SaveOutlined/>}
                        onClick={handleSave}
                    >
                        保存游戏
                    </Button>
                </div>
            </div>
        </Modal>
    );
};

export default AddGameModal;
