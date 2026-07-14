import os
import json
import isodate
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone

# 1. Configuração de Regiões (Geral/Brasil + Latam)
API_KEY = os.environ.get('YOUTUBE_API_KEY')
REGIONS = ['US', 'FR', 'NL', 'DE', 'IT', 'PT', 'BR', 'AR', 'CL', 'CO', 'ES', 'MX', 'PE']
ARQUIVO_HISTORICO = 'history.json'

def carregar_e_converter_historico():
    """Carrega o histórico e converte dados antigos (strings) para a nova estrutura JSON."""
    if not os.path.exists(ARQUIVO_HISTORICO):
        return {}
    try:
        with open(ARQUIVO_HISTORICO, 'r', encoding='utf-8') as f:
            dados = json.load(f)
    except Exception as e:
        print(f"Aviso ao carregar historico (pode estar vazio): {e}")
        return {}

    if not isinstance(dados, dict):
        return {}

    novo_historico = {}
    for vid, valor in dados.items():
        if isinstance(valor, dict):
            # Já é a nova estrutura estruturada, mantém
            novo_historico[vid] = valor
        else:
            # É uma string do histórico antigo (ex: "Data || Titulo; Link; Canal")
            data_reg = datetime.now().strftime('%Y-%m-%d')
            titulo = "Vídeo Convertido"
            link = f"https://www.youtube.com/watch?v={vid}"
            canal = "Desconhecido"
            regiao = "BR"  # Default seguro para os antigos
            rank = None
            descricao = "Registro convertido do histórico antigo."

            if isinstance(valor, str):
                if " || " in valor:
                    partes = valor.split(' || ')
                    data_reg = partes[0].strip()
                    resto = partes[1].strip() if len(partes) > 1 else ""
                    if resto:
                        sub_partes = resto.split('; ')
                        if len(sub_partes) >= 1:
                            titulo = sub_partes[0].strip()
                        if len(sub_partes) >= 2:
                            link = sub_partes[1].strip()
                        if len(sub_partes) >= 3:
                            canal = sub_partes[2].strip()
                else:
                    data_reg = valor.strip()

            novo_historico[vid] = {
                "data": data_reg,
                "titulo": titulo,
                "link": link,
                "canal": canal,
                "regiao": regiao,
                "rank": rank,
                "descricao": descricao
            }
    return novo_historico

def salvar_historico_limpo(historico_dict):
    """Filtra apenas os dados dos últimos 30 dias e salva o arquivo final."""
    data_corte = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    novo_historico = {}

    for vid, dados in historico_dict.items():
        data_do_registro = dados.get('data', '')
        if data_do_registro > data_corte:
            novo_historico[vid] = dados

    with open(ARQUIVO_HISTORICO, 'w', encoding='utf-8') as f:
        json.dump(novo_historico, f, indent=2, ensure_ascii=False)

def limpar_titulo(snippet):
    titulo = snippet['title']
    descricao = snippet.get('description', '')
    
    linhas = descricao.split('\n')
    if len(linhas) >= 3 and 'Provided to YouTube by' in linhas[0]:
        terceira_linha = linhas[2].strip()
        if terceira_linha:
            titulo = terceira_linha
            
    return titulo.replace(';', '')

def get_filtered_videos():
    if not API_KEY:
        print("ERRO: API Key não encontrada.")
        return

    youtube = build('youtube', 'v3', developerKey=API_KEY)
    data_limite_postagem = datetime.now(timezone.utc) - timedelta(days=5)
    hoje_str = datetime.now().strftime('%Y-%m-%d')
    
    # Carrega e migra o banco de dados se necessário
    historico = carregar_e_converter_historico()
    ids_sessao_atual = set()

    print(f"--- RELATÓRIO DE MONITORAMENTO: {datetime.now().strftime('%d/%m/%Y')} ---\n")

    for region in REGIONS:
        print(f"=== ESCANEANDO REGIÃO: {region} ===")
        
        def processar_itens(items):
            for idx, item in enumerate(items):
                video_id = item['id']
                
                if video_id in ids_sessao_atual: 
                    continue
                
                snippet = item['snippet']
                content = item['contentDetails']
                stats = item['statistics']
                
                views = int(stats.get('viewCount', 0))
                if region != 'BR' and views < 10000: 
                    continue
                
                if snippet.get('categoryId') != '10': 
                    continue
                
                try:
                    publicado_em = datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00'))
                    if publicado_em < data_limite_postagem: 
                        continue
                except: 
                    continue
                    
                try:
                    duracao = isodate.parse_duration(content['duration'])
                    if duracao.total_seconds() > (20 * 60): 
                        continue
                except: 
                    continue
                
                titulo_final = limpar_titulo(snippet)
                link = f"https://www.youtube.com/watch?v={video_id}"
                canal = snippet.get('channelTitle', 'Desconhecido').replace(';', '')
                descricao = snippet.get('description', '')
                
                # Rank: Se o vídeo estiver entre as posições 1 e 10 nos charts mais populares
                rank_atual = (idx + 1) if idx < 10 else None
                
                # Se já existia no histórico, atualiza preservando a data de inclusão original
                if video_id in historico:
                    data_existente = historico[video_id].get('data', hoje_str)
                    historico[video_id] = {
                        "data": data_existente,
                        "titulo": titulo_final,
                        "link": link,
                        "canal": canal,
                        "regiao": region,
                        "rank": rank_atual if rank_atual is not None else historico[video_id].get('rank'),
                        "descricao": descricao
                    }
                else:
                    historico[video_id] = {
                        "data": hoje_str,
                        "titulo": titulo_final,
                        "link": link,
                        "canal": canal,
                        "regiao": region,
                        "rank": rank_atual,
                        "descricao": descricao
                    }
                
                ids_sessao_atual.add(video_id)
                print(f"  [OK] {titulo_final} - {canal} (Rank: {rank_atual or 'Fora do Top 10'})")

        try:
            # 1. Busca os populares gerais do país (limite 50)
            req_geral = youtube.videos().list(
                part="snippet,contentDetails,statistics", chart="mostPopular", regionCode=region, maxResults=50
            ).execute()
            processar_itens(req_geral.get('items', []))
            
            # 2. Busca os populares da categoria Música (limite 30)
            req_musica = youtube.videos().list(
                part="snippet,contentDetails,statistics", chart="mostPopular", regionCode=region, videoCategoryId='10', maxResults=30
            ).execute()
            processar_itens(req_musica.get('items', []))

        except Exception as e:
            print(f"Erro ao processar região {region}: {e}")

    # Salva os arquivos e executa a limpeza de 30 dias
    salvar_historico_limpo(historico)
    print("\n--- PROCESSO CONCLUÍDO COM SUCESSO! ---")

if __name__ == "__main__":
    get_filtered_videos()
