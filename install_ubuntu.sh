#!/bin/bash
echo "🚀 Iniciando instalação do WebScraper no Ubuntu EC2..."

# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar ambiente gráfico mínimo
sudo apt install -y ubuntu-desktop-minimal
sudo apt install -y xrdp
sudo systemctl enable xrdp
sudo systemctl start xrdp

# Instalar Python e ferramentas
sudo apt install -y python3 python3-pip git curl wget unzip

# Instalar Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt update
sudo apt install -y google-chrome-stable

# Instalar nginx para proxy reverso
sudo apt install -y nginx

# Criar diretório da aplicação
sudo mkdir -p /opt/webscraper
sudo chown $USER:$USER /opt/webscraper

# Instalar dependências Python
# As dependências Python serão instaladas depois de copiar os arquivos
echo "📁 Diretório /opt/webscraper criado e pronto para receber os arquivos"

echo "✅ Instalação base concluída!"