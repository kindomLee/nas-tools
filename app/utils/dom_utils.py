class DomUtils:

    @staticmethod
    def tag_value(tag_item, tag_name, attname="", default=None):
        """
        解析XML標籤值
        """
        tagNames = tag_item.getElementsByTagName(tag_name)
        if tagNames:
            if attname:
                attvalue = tagNames[0].getAttribute(attname)
                if attvalue:
                    return attvalue
            else:
                firstChild = tagNames[0].firstChild
                if firstChild:
                    return firstChild.data
        return default

    @staticmethod
    def add_node(doc, parent, name, value=None):
        """
        新增一個DOM節點
        """
        node = doc.createElement(name)
        parent.appendChild(node)
        if value is not None:
            text = doc.createTextNode(str(value))
            node.appendChild(text)
        return node
