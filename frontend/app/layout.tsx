import "./style.css";

export const metadata={title:"Deploy Online",description:"轻量级部署管理平台"};

export default function Layout({children}:{children:React.ReactNode}){
  return <html lang="zh-CN"><body>{children}</body></html>;
}
