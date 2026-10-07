// What each back-office change is called (AD-06), for the audit page and the activity beside a
// thing (AD-07).

/** What each back-office change is called, by its route. */
export const ACTION_LABEL: Record<string, string> = {
  "/api/companies": "建立公司",
  "/api/companies/{company_id}/office-theme": "辦公室風格",
  "/api/companies/{company_id}/agents/{agent_id}/pause": "暫停代理",
  "/api/companies/{company_id}/agents/{agent_id}/resume": "恢復代理",
  "/api/companies/{company_id}/agents/{agent_id}/retire": "解雇代理",
  "/api/companies/{company_id}/agents": "雇用代理",
  "/api/approvals/{approval_id}/decide": "審批決定",
  "/api/companies/{company_id}/workflows/{workflow_run_id}/restart": "重跑工作流程",
  "/api/companies/{company_id}/workflows": "啟動工作流程",
  "/api/companies/{company_id}/finance/budgets": "設定預算",
  "/api/companies/{company_id}/finance/capital": "增資",
  "/api/companies/{company_id}/projects/{project_id}/pause": "暫停專案",
  "/api/companies/{company_id}/projects/{project_id}/resume": "恢復專案",
  "/api/admin/memberships/comps": "授予 VIP",
  "/api/admin/memberships/comps/{grant_id}/revoke": "撤銷 VIP",
  "/api/admin/coins/adjustments": "調整鯨幣",
  "/api/stories/{story_id}/start": "開始製作",
  "/api/articles/{article_id}/cover/swap": "換一張首圖",
  "/api/articles/{article_id}/cover/search": "重找首圖",
  "/api/articles/{article_id}/cover/ask": "請行銷換圖",
  "/api/articles/{article_id}/cover": "拿掉首圖",
  "/api/articles/{article_id}/access": "閱讀權限",
  "/api/articles/{article_id}/section": "文章分類",
  "/api/articles/{article_id}/unpublish": "下架",
  "/api/articles/{article_id}/republish": "重新上架",
  "/api/articles/{article_id}/revise": "修改文章",
  "/api/companies/{company_id}/sources": "新增來源",
  "/api/companies/{company_id}/team/messages": "團隊群組留言",
};
