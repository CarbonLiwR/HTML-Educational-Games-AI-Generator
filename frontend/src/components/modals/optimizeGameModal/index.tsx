import React, {useState, useRef, useEffect} from "react";
import {Modal, Input, Button, Spin, Popover, message} from "antd";
import {CaretRightOutlined, VerticalAlignBottomOutlined, BookOutlined, CodeOutlined} from "@ant-design/icons";
import {getToken} from "../../../utils/auth.ts";
import pako from "pako";

const generateUUID = () => {
    return Math.random().toString(36).substring(2, 10).toUpperCase();
};
const OptimizeModal = ({visible, onClose, saveCode, gameToOptimize}) => {
    const [userMessage, setUserMessage] = useState("");
    const [gameOptimize, setGameOptimize] = useState({}); // 当前游戏内容
    const [game, setGame] = useState({});//游戏记录
    const [messages, setMessages] = useState([]); // 聊天记录
    const [loading, setLoading] = useState(false); // AI加载状态
    const chatContainerRef = useRef(null);
    const token = getToken();


    const runHtmlCode = (code) => {
        const newWindow = window.open("", "_blank", "width=1000,height=800");
        if (newWindow) {
            newWindow.document.open();
            newWindow.document.write(code);
            newWindow.document.close();
        } else {
            alert("弹出窗口被阻止，请允许弹出窗口后重试");
        }
    };

    const cleanExtractedData = async (data) => {
        // 检查 data 是否存在
        if (!data) {
            return {
                uuid: data?.uuid || "",
                name: "",
                rules: data?.rules || "", // 修复：确保 rules 正常传递
                code: "",
            };
        }

        // 检查并确保字段存在
        const name = typeof data.name === "string" ? data.name : "";
        const code = typeof data.code === "string" ? data.code : "";
        const rules = typeof data.rules === "string" ? data.rules : ""; // 修复：确保 rules 是字符串

        // 清洗 name：删除所有 Markdown 格式符号
        const cleanName = name.replace(/[_*~`>#+\-\$\$$$]/g, "");

        // 清洗 code：去除 '''html 到 ''' 的内容，并提取 HTML 块
        // console.log("原内容"+data.code);
        let cleanResult = code.replace(/'''html[\s\S]*?'''/gi, ""); // 去除 '''html 标记及其内容
        const htmlMatch = cleanResult.match(/(?:<!DOCTYPE html>\s*)?<html[\s\S]*?>[\s\S]*?<\/html>/i);
        const cleanCode = htmlMatch ? htmlMatch[0] : "";

        return {
            uuid: data.uuid || "",
            name: cleanName,
            rules: rules, // 保留原始规则
            code: cleanCode,
        };
    };


    const optimizeGame = async (game, query) => {
        try {
            // 构建请求数据
            const requestData = {
                code: game.code, // 从游戏对象中提取代码
                question: query, // 用户输入的优化需求
                user_token: token, // 用户令牌（假设从外部获取）
            };

            const response = await fetch('http://localhost:8000/api/v1/game/optimize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData), // 将对象转为 JSON 字符串
            });

            if (!response.body) {
                throw new Error("No response body");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");

            let optimizedResult = null; // 存储优化后的结果

            while (true) {
                const {value, done} = await reader.read();
                if (done) break;

                const lines = decoder.decode(value).split("\n").filter(Boolean);
                for (const line of lines) {
                    try {
                        const data = JSON.parse(line); // 解析流中的 JSON 数据
                        if (data.type === "heartbeat") {
                            console.log("❤️ 心跳");
                        } else if (data.type === "answer") {
                            console.log(data);
                            const uuid = generateUUID();
                            const extractedData = {
                                uuid: uuid,
                                name: data.game_name,
                                rules: data.game_rules,
                                code: data.result,
                            };
                            // console.log("清理前内容"+JSON.stringify(extractedData.rules));
                            const cleanedData = await cleanExtractedData(extractedData);
                            // console.log("清理后内容"+JSON.stringify(cleanedData.rules));
                            optimizedResult = cleanedData;
                        }
                    } catch (error) {
                        console.error("JSON parse error:", error, line);
                    }
                }
            }

            if (optimizedResult) {
                // console.log("优化结果:", JSON.stringify(optimizedResult));

                // 更新游戏内容
                const updatedGame = {
                    uuid: optimizedResult.uuid,
                    name: optimizedResult.name, // 从 extractCode 中获取 name 或补充后的 name
                    rules: optimizedResult.rules, // 从 extractCode 中获取 rules 或补充后的 rules
                    code: optimizedResult.code, // 从 extractCode 中获取 code
                };
                message.success("游戏优化成功！");
                return updatedGame; // 返回优化后的游戏
            } else {
                message.error("游戏优化失败！");
                return null;
            }
        } catch (error) {
            console.error("优化失败:", error);
            message.error("优化失败，请重试！");
            return null;
        }
    };
    // 处理优化请求
    const handleOptimize = async (message) => {
        // 显示用户消息
        setMessages((prevMessages) => [
            ...prevMessages,
            {sender: "user", text: message}, // 用户消息立即显示
        ]);

        setLoading(true); // 设置加载状态
        // console.log("优化请求:", message);
        // console.log("当前游戏内容:", gameOptimize);
        // return
        // 调用优化函数
        const optimizedGame = await optimizeGame(gameOptimize, message); // 调用传入的优化函数，返回最新的 game

        setLoading(false); // 取消加载状态

        if (optimizedGame) {
            // 更新 gameToOptimize 和添加优化结果到聊天记录
            setGame(optimizedGame);
            setMessages((prevMessages) => [
                ...prevMessages,
                {sender: "bot", isCode: true, uuid: optimizedGame.uuid, game: optimizedGame}, // 优化结果
            ]);
        }
    };
    // 初始化聊天记录
    useEffect(() => {
        if (gameToOptimize) {
            // console.log(gameToOptimize);
            setGameOptimize(gameToOptimize);
            const defaultMessage = {
                sender: "bot",
                isCode: true,
                uuid: gameToOptimize.uuid,
                game: gameToOptimize,
            };
            setMessages([defaultMessage]);
            setGame((prevGame) => ({
                ...prevGame, // 保留之前的所有游戏数据
                [gameToOptimize.uuid]: {
                    uuid: gameToOptimize.uuid,
                    name: gameToOptimize.name || "", // 确保 name 有值
                    rules: gameToOptimize.rules || "", // 确保 rules 有值
                    code: gameToOptimize.code, // 确保 code 有值
                },
            }));
        }
    }, [gameToOptimize]);
    // 自动滚动到最新消息
    useEffect(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
    }, [messages]);


    return (
        <Modal
            title="优化游戏"
            visible={visible}
            onCancel={onClose}
            footer={null}
            width="80%"
            style={{top: 20}}
        >
            <div
                style={{
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    height: "80vh",
                    padding: "16px",
                    backgroundColor: "#ffffff",
                }}
            >
                {/* 聊天记录容器 */}
                <div
                    style={{
                        flex: 1,
                        overflowY: "auto",
                        border: "1px solid #e8e8e8",
                        borderRadius: "8px",
                        padding: "16px",
                        backgroundColor: "#f5f5f5",
                        marginBottom: "16px",
                    }}
                    ref={chatContainerRef}
                >
                    {messages.map((msg, index) => (
                        msg.sender === "bot" ? (
                            msg.isCode ? (
                                // 如果是代码块，渲染矩形运行框
                                <div
                                    key={index}
                                    style={{
                                        border: "1px solid #e8e8e8",
                                        borderRadius: "8px",
                                        padding: "16px",
                                        marginBottom: "16px",
                                        backgroundColor: "#ffffff",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center",
                                            borderRadius: "8px",
                                            backgroundColor: "#ffffff",
                                        }}
                                    >
                                        {/* 左侧内容：显示名称 */}
                                        <div style={{fontWeight: "bold", fontSize: "16px", color: "#333"}}>
                                            <CodeOutlined/> {msg.game?.name || "新游戏"} {/* 动态显示名称 */}
                                        </div>
                                        <Popover
                                            content={
                                                <div style={{maxWidth: "300px", wordWrap: "break-word"}}>
                                                    {msg.game?.rules || "暂无规则"} {/* 动态显示规则 */}
                                                </div>
                                            }
                                            title="游戏规则"
                                        >
                                            <Button style={{border: "none"}}>
                                                <BookOutlined/>规则
                                            </Button>
                                        </Popover>
                                        {/* 右侧按钮区域 */}
                                        <div
                                            style={{
                                                display: "flex",
                                                // flexDirection: "column",
                                                alignItems: "center",
                                                gap: "8px",
                                            }}
                                        >
                                            <Button
                                                onClick={() => {
                                                    const newHtmlCode = msg.game?.code;
                                                    runHtmlCode(newHtmlCode); // 更新 htmlCode
                                                }}
                                            >
                                                <CaretRightOutlined/>运行
                                            </Button>
                                            <Button
                                                onClick={() => saveCode(msg.game)}
                                            >
                                                <VerticalAlignBottomOutlined/>保存
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                // 如果不是代码块，渲染普通对话框
                                <div key={index} style={{textAlign: "left"}}>
                                    <div
                                        style={{
                                            display: "inline-block",
                                            margin: "5px",
                                            padding: "10px",
                                            borderRadius: "5px",
                                            backgroundColor: "#f0f0f0",
                                            whiteSpace: "pre-line",
                                            lineHeight: "1.5",
                                        }}
                                    >
                                        {msg.text.replace(/[#*-]/g, "")}
                                    </div>
                                </div>
                            )
                        ) : (
                            // 用户消息
                            <div key={index} style={{textAlign: "right"}}>
                                <div
                                    style={{
                                        display: "inline-block",
                                        margin: "5px",
                                        padding: "10px",
                                        borderRadius: "5px",
                                        backgroundColor: "#e6f7ff",
                                        whiteSpace: "pre-line",
                                        lineHeight: "1.5",
                                    }}
                                >
                                    {msg.text.replace(/[#*-]/g, "")}
                                </div>
                            </div>
                        )
                    ))}
                    {loading && messages.length > 0 && messages[messages.length - 1].sender === "user" && (
                        <div style={{textAlign: "left", padding: "10px"}}>
                            <strong style={{color: "skyblue", marginRight: "6px"}}>
                                游戏正在优化中，请耐心等待5分钟
                            </strong>
                            <Spin tip="优化中..."/>
                        </div>
                    )}
                </div>

                {/* 输入框与发送按钮 */}
                <div
                    style={{
                        display: "flex",
                        gap: "10px",
                        width: "100%",
                        justifyContent: "center",
                    }}
                >
                    <Input
                        value={userMessage}
                        onChange={(e) => setUserMessage(e.target.value)}
                        onPressEnter={(e) => {
                            e.preventDefault();
                            handleOptimize(userMessage); // 传递用户消息
                            setUserMessage(""); // 清空输入框
                        }}
                        placeholder="请告诉我您对游戏内容的优化建议..."
                        style={{
                            flex: 1,
                            borderRadius: "4px",
                            border: "1px solid #e8e8e8",
                            padding: "8px",
                        }}
                    />
                    <Button
                        onClick={() => {
                            handleOptimize(userMessage);
                            setUserMessage("");
                        }}
                        loading={loading}
                        style={{
                            height: "100%",
                            borderRadius: "4px",
                        }}
                    >
                        {loading ? "优化中..." : "发送"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
};

export default OptimizeModal;
