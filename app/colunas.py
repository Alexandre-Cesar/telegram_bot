"""Colunas do registro e do relatório diário (abrem direto no Excel)."""
COLUNAS = [
    "registrado_em", "usuario", "tipo_sinal", "acao_servico", "tipo_automatico",
    "categoria_vertical", "modelo_placa", "rua", "bairro", "cidade",
    "latitude", "longitude", "tamanho_m2", "material", "padrao_catalogo",
    "fotos", "link_foto_antes", "link_foto_depois", "confianca_extracao",
]

COLUNAS_RELATORIO = [
    "enviado_em", "data_referencia", "modo_envio", "usuario", "veiculo", "ajudantes",
    "total_servicos", "implantacoes", "substituicoes", "remocoes",
    "outros_servicos", "total_m2", "ruas_atendidas", "ultimo_registro_incluido",
]
